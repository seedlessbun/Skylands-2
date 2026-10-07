// C entry point for Python (ctypes): LZO1X decompression via lzokay (MIT).
#include "lzokay.hpp"
#include <cstddef>
#include <cstdint>

#if defined(_WIN32)
#define EXPORT extern "C" __declspec(dllexport)
#else
#define EXPORT extern "C" __attribute__((visibility("default")))
#endif

// Returns bytes written, or a negative lzokay::EResult on error.
EXPORT long long skylands_lzo_decompress(const uint8_t* src, size_t src_size, uint8_t* dst, size_t dst_size) {
    size_t out_size = 0;
    lzokay::EResult r = lzokay::decompress(src, src_size, dst, dst_size, out_size);
    if (r < lzokay::EResult::Success) return static_cast<long long>(r);
    return static_cast<long long>(out_size);
}
