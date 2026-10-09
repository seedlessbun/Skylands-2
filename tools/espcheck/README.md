Test-only structural check of a generated plugin using the `esplugin` crate (what LOOT uses; GPL-3.0, not shipped).

    cd tools/espcheck && cargo build --release
    ESPCHECK=$PWD/target/release/espcheck python -m pytest tests/test_generate.py
