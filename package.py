name = "editorial"
title = "Editorial"
version = "0.2.0+dev"
client_dir = "ayon_editorial"

ayon_server_version = ">=1.1.2"
ayon_required_addons = {
    "core": ">=1.8.0",
}
# Hosts follow editorial (MVP.md, "Releases"): a warning only, so
# editorial can be released first.
ayon_compatible_addons = {
    "applications": ">=1.0.0",
    "hiero": ">=0.7.0",
    "flame": ">=1.5.0",
}
