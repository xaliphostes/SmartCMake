#include "imgfx/filters.hpp"

namespace imgfx {

Image invert(const Image& src)
{
    Image out = src;
    for (auto& pixel : out.pixels)
        pixel = static_cast<std::uint8_t>(255 - pixel);
    return out;
}

}  // namespace imgfx
