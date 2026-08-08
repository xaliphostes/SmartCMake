#include "imgfx/image.hpp"

#include <istream>
#include <ostream>
#include <string>

namespace imgfx {

namespace {

std::uint8_t clamp_byte(int value)
{
    if (value < 0)
        return 0;
    if (value > 255)
        return 255;
    return static_cast<std::uint8_t>(value);
}

}  // namespace

Image read_pgm(std::istream& in)
{
    std::string magic;
    int width = 0;
    int height = 0;
    int maxval = 0;
    if (!(in >> magic >> width >> height >> maxval))
        return {};
    if (magic != "P2" || width <= 0 || height <= 0)
        return {};

    Image image(width, height);
    for (auto& pixel : image.pixels) {
        int value = 0;
        if (!(in >> value))
            return {};
        pixel = clamp_byte(value);
    }
    return image;
}

void write_pgm(const Image& image, std::ostream& out)
{
    out << "P2\n" << image.width << ' ' << image.height << "\n255\n";
    for (int y = 0; y < image.height; ++y) {
        for (int x = 0; x < image.width; ++x)
            out << static_cast<int>(image.at(x, y))
                << (x + 1 == image.width ? '\n' : ' ');
    }
}

}  // namespace imgfx
