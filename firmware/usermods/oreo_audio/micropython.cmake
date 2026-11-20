add_library(usermod_oreo_audio INTERFACE)

target_sources(usermod_oreo_audio INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}/modoreo_audio.c
    # minimp3 (CC0), vendored in minimp3/ (see minimp3/VENDORED.md)
    ${CMAKE_CURRENT_LIST_DIR}/mp3_core.c
)

target_include_directories(usermod_oreo_audio INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}
)

target_link_libraries(usermod INTERFACE usermod_oreo_audio)
