// Hardware-timed IR envelope receiver for OreoOS on ESP32-S3.
//
// The TSOP38238 demodulates the optical carrier and drives GPIO18 low during
// each carrier burst. ESP-IDF RMT records that envelope at 1 us resolution,
// independently of MicroPython, display flushes, and garbage collection.
//
// Glitch filter limit (issue #48)
// -------------------------------
// rmt_receive() validates signal_range_min_ns against the RX glitch filter:
//
//     filter_reg = filter_clock_hz * signal_range_min_ns / 1e9
//     filter_reg must be <= RMT_LL_MAX_FILTER_VALUE (255 on the S3)
//
// On the ESP32-S3 the filter counts at the RMT *group* clock, not at the
// channel resolution. Asking for a 1 MHz channel from the 80 MHz APB source
// leaves the group prescaler at 1, so the filter runs at 80 MHz and the
// longest accepted value is 255 / 80 MHz = 3187 ns. The old 20 us filter
// computed a register value of 1600 and every rmt_receive() returned
// ESP_ERR_INVALID_ARG ("RMT RX arm failed"). The TSOP already removes the
// carrier, and real IR marks are hundreds of microseconds long, so a ~3 us
// filter rejects pin noise without touching real data. If some other channel
// set a faster group clock first, arming steps down to 1 us and then to no
// filter instead of failing.

#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#include "py/runtime.h"

#include "driver/gpio.h"
#include "driver/rmt_rx.h"
#include "esp_err.h"
#include "esp_heap_caps.h"

#define OREO_IR_RESOLUTION_HZ (1000000U)
#define OREO_IR_MAX_SYMBOLS   (512U)
// DMA mode: size of the DMA staging block. Non-DMA mode: on-chip RMT RAM.
// The S3 has 48 words per block and the channel must own a whole number of
// blocks, so 48 claims exactly one block and leaves room for the TX channel.
// Ping-pong RX keeps frames longer than one block intact.
#define OREO_IR_DMA_SYMBOLS   (64U)
#define OREO_IR_MEM_SYMBOLS   (48U)
// 25 ms of silence ends a frame: 25000 ticks at 1 MHz, below the 32767 limit.
#define OREO_IR_IDLE_NS       (25000000U)

// Glitch filter candidates, longest first (see the header comment).
static const uint32_t s_min_ns_steps[] = {3000U, 1000U, 0U};
#define OREO_IR_MIN_STEPS (sizeof(s_min_ns_steps) / sizeof(s_min_ns_steps[0]))

static rmt_channel_handle_t s_rx_channel;
static rmt_symbol_word_t *s_symbols;
static volatile size_t s_symbol_count;
static volatile bool s_frame_ready;
static bool s_started;
static bool s_with_dma;
static int s_rx_gpio = -1;
static const char *s_last_stage = "idle";
static esp_err_t s_last_err = ESP_OK;

static rmt_receive_config_t s_receive_config = {
    .signal_range_min_ns = 3000U,
    .signal_range_max_ns = OREO_IR_IDLE_NS,
};

static NORETURN void oreo_ir_raise(esp_err_t err, const char *operation) {
    s_last_stage = operation;
    s_last_err = err;
    mp_raise_msg_varg(&mp_type_OSError,
        MP_ERROR_TEXT("%s failed: %s (dma=%d, filter=%uns)"),
        operation, esp_err_to_name(err), (int)s_with_dma,
        (unsigned int)s_receive_config.signal_range_min_ns);
}

static bool IRAM_ATTR oreo_ir_rx_done(
    rmt_channel_handle_t channel,
    const rmt_rx_done_event_data_t *event,
    void *context
) {
    (void)channel;
    (void)context;
    s_symbol_count = event->num_symbols;
    s_frame_ready = true;
    return false;
}

static esp_err_t oreo_ir_arm(void) {
    s_symbol_count = 0;
    s_frame_ready = false;
    return rmt_receive(
        s_rx_channel,
        s_symbols,
        OREO_IR_MAX_SYMBOLS * sizeof(rmt_symbol_word_t),
        &s_receive_config
    );
}

// First arm on a fresh channel: walk the glitch filter down until the driver
// accepts it. Only ESP_ERR_INVALID_ARG is retried; buffer problems fail on
// every step and report the last error.
static esp_err_t oreo_ir_arm_first(void) {
    esp_err_t err = ESP_ERR_INVALID_ARG;
    for (size_t i = 0; i < OREO_IR_MIN_STEPS; ++i) {
        s_receive_config.signal_range_min_ns = s_min_ns_steps[i];
        err = oreo_ir_arm();
        if (err != ESP_ERR_INVALID_ARG) {
            break;
        }
    }
    return err;
}

// Disable and delete the channel. The symbol buffer is left alone: the caller
// frees it only once the channel is gone, so RMT/DMA can never write into
// released memory.
static esp_err_t oreo_ir_close_channel(void) {
    if (s_rx_channel == NULL) {
        return ESP_OK;
    }
    // rmt_disable() accepts ENABLE and RUN and reports INVALID_STATE for a
    // channel that never got enabled; deletion is what matters.
    esp_err_t disable_err = rmt_disable(s_rx_channel);
    esp_err_t delete_err = rmt_del_channel(s_rx_channel);
    if (delete_err != ESP_OK) {
        return disable_err != ESP_OK ? disable_err : delete_err;
    }
    s_rx_channel = NULL;
    return ESP_OK;
}

static esp_err_t oreo_ir_stop_internal(void) {
    esp_err_t cleanup_err = oreo_ir_close_channel();
    if (s_rx_channel == NULL) {
        if (s_symbols != NULL) {
            heap_caps_free(s_symbols);
            s_symbols = NULL;
        }
        s_symbol_count = 0;
        s_frame_ready = false;
        s_started = false;
        s_rx_gpio = -1;
    }
    return cleanup_err;
}

// Create, hook up and enable one RX channel. On failure the channel is closed
// again and *stage names the step that failed.
static esp_err_t oreo_ir_open_channel(int pin, bool with_dma, const char **stage) {
    rmt_rx_channel_config_t channel_config = {
        .clk_src = RMT_CLK_SRC_DEFAULT,
        .resolution_hz = OREO_IR_RESOLUTION_HZ,
        .mem_block_symbols = with_dma ? OREO_IR_DMA_SYMBOLS : OREO_IR_MEM_SYMBOLS,
        .gpio_num = (gpio_num_t)pin,
        .flags.with_dma = with_dma,
    };
    s_with_dma = with_dma;
    *stage = "RMT RX channel";
    esp_err_t err = rmt_new_rx_channel(&channel_config, &s_rx_channel);
    if (err != ESP_OK) {
        s_rx_channel = NULL;
        return err;
    }
    // Channel creation routes the pin through the GPIO matrix; keep the TSOP
    // open-collector output pulled up so an idle line reads HIGH.
    gpio_set_pull_mode((gpio_num_t)pin, GPIO_PULLUP_ONLY);

    rmt_rx_event_callbacks_t callbacks = {
        .on_recv_done = oreo_ir_rx_done,
    };
    *stage = "RMT RX callback";
    err = rmt_rx_register_event_callbacks(s_rx_channel, &callbacks, NULL);
    if (err == ESP_OK) {
        *stage = "RMT RX enable";
        err = rmt_enable(s_rx_channel);
    }
    if (err == ESP_OK) {
        *stage = "RMT RX arm";
        err = oreo_ir_arm_first();
    }
    if (err != ESP_OK) {
        oreo_ir_close_channel();
    }
    return err;
}

static mp_obj_t oreo_ir_start(mp_obj_t pin_obj) {
    int pin = mp_obj_get_int(pin_obj);
    if (!GPIO_IS_VALID_GPIO(pin)) {
        mp_raise_ValueError(MP_ERROR_TEXT("invalid IR RX GPIO"));
    }

    // App redraws and tab transitions can request the same receiver twice.
    // Treat that as success instead of tearing down a live transaction.
    if (s_started && s_rx_gpio == pin && s_rx_channel != NULL) {
        return mp_const_none;
    }

    esp_err_t err = oreo_ir_stop_internal();
    if (err != ESP_OK) {
        oreo_ir_raise(err, "RMT RX cleanup");
    }

    // Internal, DMA-capable and 64-byte aligned: satisfies the GDMA alignment
    // and the IDF-8997 "internal RAM only" rule. 512 words (2 KiB) fits well
    // inside the two DMA descriptors the driver allocates (2 x 4092 bytes).
    s_symbols = heap_caps_aligned_calloc(
        64,
        OREO_IR_MAX_SYMBOLS,
        sizeof(rmt_symbol_word_t),
        MALLOC_CAP_8BIT | MALLOC_CAP_INTERNAL | MALLOC_CAP_DMA
    );
    if (s_symbols == NULL) {
        mp_raise_msg(&mp_type_MemoryError, MP_ERROR_TEXT("IR RX buffer"));
    }

    gpio_set_pull_mode((gpio_num_t)pin, GPIO_PULLUP_ONLY);

    // DMA first; the S3 has a single DMA-capable RX channel and GDMA is shared
    // with the display, so fall back to the on-chip ping-pong path whenever
    // the DMA attempt fails at any stage. Timing is hardware-exact either way.
    const char *stage = "RMT RX channel";
    err = oreo_ir_open_channel(pin, true, &stage);
    if (err != ESP_OK) {
        err = oreo_ir_open_channel(pin, false, &stage);
    }
    if (err != ESP_OK) {
        oreo_ir_stop_internal();
        oreo_ir_raise(err, stage);
    }

    s_started = true;
    s_rx_gpio = pin;
    s_last_stage = "listening";
    s_last_err = ESP_OK;
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(oreo_ir_start_obj, oreo_ir_start);

static mp_obj_t oreo_ir_stop(void) {
    esp_err_t err = oreo_ir_stop_internal();
    if (err != ESP_OK) {
        oreo_ir_raise(err, "RMT RX stop");
    }
    s_last_stage = "idle";
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(oreo_ir_stop_obj, oreo_ir_stop);

static mp_obj_t oreo_ir_poll(void) {
    if (!s_started || !s_frame_ready) {
        return mp_const_none;
    }

    size_t symbol_count = s_symbol_count;
    if (symbol_count > OREO_IR_MAX_SYMBOLS) {
        symbol_count = OREO_IR_MAX_SYMBOLS;
    }

    // The TSOP is idle HIGH and marks are LOW. Drop any leading idle segment,
    // then return alternating mark/space durations independent of pin polarity.
    mp_obj_t *durations = m_new(mp_obj_t, symbol_count * 2 + 1);
    size_t duration_count = 0;
    bool found_mark = false;
    for (size_t i = 0; i < symbol_count; ++i) {
        const rmt_symbol_word_t symbol = s_symbols[i];
        const uint16_t widths[2] = {symbol.duration0, symbol.duration1};
        const uint8_t levels[2] = {symbol.level0, symbol.level1};
        for (size_t part = 0; part < 2; ++part) {
            uint16_t width = widths[part];
            if (width == 0) {
                continue;
            }
            if (!found_mark) {
                if (levels[part] != 0) {
                    continue;
                }
                found_mark = true;
            }
            durations[duration_count++] = mp_obj_new_int_from_uint(width);
        }
    }

    // Copy out before re-arming: the next transaction writes into s_symbols.
    s_frame_ready = false;
    s_symbol_count = 0;
    esp_err_t err = oreo_ir_arm();
    if (err != ESP_OK) {
        m_del(mp_obj_t, durations, symbol_count * 2 + 1);
        oreo_ir_stop_internal();
        oreo_ir_raise(err, "RMT RX rearm");
    }

    if (duration_count == 0) {
        m_del(mp_obj_t, durations, symbol_count * 2 + 1);
        return mp_const_none;
    }
    mp_obj_t result = mp_obj_new_tuple(duration_count, durations);
    m_del(mp_obj_t, durations, symbol_count * 2 + 1);
    return result;
}
static MP_DEFINE_CONST_FUN_OBJ_0(oreo_ir_poll_obj, oreo_ir_poll);

static mp_obj_t oreo_ir_active(void) {
    return mp_obj_new_bool(s_started);
}
static MP_DEFINE_CONST_FUN_OBJ_0(oreo_ir_active_obj, oreo_ir_active);

// Diagnostics for the Quest app and serial debugging:
// (active, gpio, dma, filter_ns, stage, last_error_name)
static mp_obj_t oreo_ir_info(void) {
    mp_obj_t items[6] = {
        mp_obj_new_bool(s_started),
        mp_obj_new_int(s_rx_gpio),
        mp_obj_new_bool(s_with_dma),
        mp_obj_new_int_from_uint(s_receive_config.signal_range_min_ns),
        mp_obj_new_str(s_last_stage, strlen(s_last_stage)),
        mp_obj_new_str(esp_err_to_name(s_last_err), strlen(esp_err_to_name(s_last_err))),
    };
    return mp_obj_new_tuple(6, items);
}
static MP_DEFINE_CONST_FUN_OBJ_0(oreo_ir_info_obj, oreo_ir_info);

static const mp_rom_map_elem_t oreo_ir_module_globals_table[] = {
    {MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR__oreo_ir)},
    {MP_ROM_QSTR(MP_QSTR_start), MP_ROM_PTR(&oreo_ir_start_obj)},
    {MP_ROM_QSTR(MP_QSTR_stop), MP_ROM_PTR(&oreo_ir_stop_obj)},
    {MP_ROM_QSTR(MP_QSTR_poll), MP_ROM_PTR(&oreo_ir_poll_obj)},
    {MP_ROM_QSTR(MP_QSTR_active), MP_ROM_PTR(&oreo_ir_active_obj)},
    {MP_ROM_QSTR(MP_QSTR_info), MP_ROM_PTR(&oreo_ir_info_obj)},
};
static MP_DEFINE_CONST_DICT(oreo_ir_module_globals, oreo_ir_module_globals_table);

const mp_obj_module_t oreo_ir_module = {
    .base = {&mp_type_module},
    .globals = (mp_obj_dict_t *)&oreo_ir_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR__oreo_ir, oreo_ir_module);
