#include "imgfx/filters.hpp"

namespace imgfx {

/// 3x3 box blur. The window is clipped at the edges, so a corner averages the
/// four pixels that exist rather than reading past the buffer.
Image blur(const Image& src)
{
    Image out(src.width, src.height);
    for (int y = 0; y < src.height; ++y) {
        for (int x = 0; x < src.width; ++x) {
            int sum = 0;
            int count = 0;
            for (int dy = -1; dy <= 1; ++dy) {
                for (int dx = -1; dx <= 1; ++dx) {
                    const int nx = x + dx;
                    const int ny = y + dy;
                    if (nx < 0 || ny < 0 || nx >= src.width || ny >= src.height)
                        continue;
                    sum += src.at(nx, ny);
                    ++count;
                }
            }
            out.at(x, y) = static_cast<std::uint8_t>(sum / count);
        }
    }
    return out;
}

}  // namespace imgfx
