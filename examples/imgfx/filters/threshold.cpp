#include "imgfx/filters.hpp"

// Supplied by build.scmake, from this filter's row of the table:
//
//     { name: "threshold", ..., defines: ["IMGFX_THRESHOLD=96"] }
//
// The fallback keeps the file compilable on its own; the build never uses it.
#ifndef IMGFX_THRESHOLD
#define IMGFX_THRESHOLD 128
#endif

namespace imgfx {

Image threshold(const Image& src)
{
    Image out = src;
    for (auto& pixel : out.pixels)
        pixel = pixel < IMGFX_THRESHOLD ? 0 : 255;
    return out;
}

}  // namespace imgfx
