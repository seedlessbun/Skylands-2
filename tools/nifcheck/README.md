Test-only NIF checker built on nifly (GPL-3.0, github.com/ousnius/nifly); never shipped.

    git clone https://github.com/ousnius/nifly && cmake -S nifly -B nifly/build && cmake --build nifly/build
    g++ -std=c++17 -Inifly/include -Inifly/external check.cpp nifly/build/src/libnifly.a -o check
    NIFCHECK=$PWD/check python -m pytest tests/test_nif.py
