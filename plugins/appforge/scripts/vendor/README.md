Vendored pure-Python PyYAML 6.0.3 (MIT License, (c) 2017-2021 Ingy döt Net, (c) 2006-2016 Kirill Simonov),
used only when PyYAML is not installed, so that the plugin works with a bare `python3`.
The optional C extension (cyaml) is not included: `import yaml` falls back to the pure-Python loader.
