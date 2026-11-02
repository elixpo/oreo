# Doom engine (GPL-2.0-or-later) as the _oreo_doom module. See README.md.
set(OREO_DOOM_DIR ${CMAKE_CURRENT_LIST_DIR})

# The engine is an object library linked straight into the firmware, like
# MicroPython's own btree. Kept apart from the module sources, its files skip
# MicroPython's QSTR scan (which has none of their include paths) and keep
# their settings to themselves: include paths with generic names such as
# config.h, CMAP256, the exit() redirect and -w (vendored code is left as
# upstream wrote it; ESP-IDF builds with -Werror=all).
file(GLOB OREO_DOOM_ENGINE ${OREO_DOOM_DIR}/engine/*.c)
add_library(oreo_doom_engine OBJECT
    ${OREO_DOOM_ENGINE}
    ${OREO_DOOM_DIR}/port/oreo_doomgeneric.c
    ${OREO_DOOM_DIR}/port/w_file_owz.c
)
target_include_directories(oreo_doom_engine PRIVATE
    ${OREO_DOOM_DIR}/port
    ${OREO_DOOM_DIR}/engine
)
target_compile_definitions(oreo_doom_engine PRIVATE CMAP256 OREO_DOOM_BADGE)
# ESP-IDF's options (optimisation, sections) arrive on the usermod target
# after this file is read, hence the generator expression.
target_compile_options(oreo_doom_engine PRIVATE
    $<TARGET_PROPERTY:usermod,INTERFACE_COMPILE_OPTIONS>
    -include ${OREO_DOOM_DIR}/port/oreo_doom_port.h
    -w
)

add_library(usermod_oreo_doom INTERFACE)
target_sources(usermod_oreo_doom INTERFACE ${OREO_DOOM_DIR}/moddoom.c)
target_include_directories(usermod_oreo_doom INTERFACE ${OREO_DOOM_DIR})
target_link_libraries(usermod_oreo_doom INTERFACE $<TARGET_OBJECTS:oreo_doom_engine>)

target_link_libraries(usermod INTERFACE usermod_oreo_doom)
