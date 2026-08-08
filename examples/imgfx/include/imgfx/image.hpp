#pragma once

#include <cstddef>
#include <cstdint>
#include <iosfwd>
#include <vector>

namespace imgfx
{

    /// An 8-bit greyscale image, stored row-major.
    struct Image
    {
        int width = 0;
        int height = 0;
        std::vector<std::uint8_t> pixels;

        Image() = default;

        Image(int w, int h)
            : width(w), height(h), pixels(static_cast<std::size_t>(w) * h, 0)
        {
        }

        std::uint8_t &at(int x, int y) { return pixels[index(x, y)]; }
        std::uint8_t at(int x, int y) const { return pixels[index(x, y)]; }

    private:
        std::size_t index(int x, int y) const
        {
            return static_cast<std::size_t>(y) * width + x;
        }
    };

    /// Reads the ASCII PGM (P2) subset that write_pgm produces. Returns an empty
    /// image if the stream does not start with a P2 header.
    Image read_pgm(std::istream &in);

    void write_pgm(const Image &image, std::ostream &out);

} // namespace imgfx
