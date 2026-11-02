// SPDX-License-Identifier: GPL-2.0-or-later
// Build configuration for the Doom engine on the Oreo Badge (replaces the
// autoconf-generated config.h of Chocolate Doom / doomgeneric).

#ifndef OREO_DOOM_CONFIG_H
#define OREO_DOOM_CONFIG_H

#define PACKAGE "oreo-doom"
#define PACKAGE_NAME "Doom"
#define PACKAGE_TARNAME "oreo-doom"
#define PACKAGE_VERSION "1.0"
#define PACKAGE_STRING "Doom (Oreo Badge)"
#define PACKAGE_URL "https://github.com/elixpo/oreo"
#define PACKAGE_BUGREPORT "https://github.com/elixpo/oreo/issues"
#define PROGRAM_PREFIX "oreo-"
#define VERSION PACKAGE_VERSION

// Directory searched for IWADs; the badge passes -iwad owz:... instead.
#define FILES_DIR "."

#define STDC_HEADERS 1
#define HAVE_INTTYPES_H 1
#define HAVE_STDINT_H 1
#define HAVE_STDLIB_H 1
#define HAVE_STRING_H 1
#define HAVE_STRINGS_H 1
#define HAVE_SYS_TYPES_H 1

#endif
