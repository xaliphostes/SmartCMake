#include <iostream>
#include <string>

#include "imgfx/filters.hpp"
#include "imgfx/image.hpp"

int main(int argc, char** argv)
{
    if (argc < 2) {
        std::cerr << "usage: imgfx <filter>... < in.pgm > out.pgm\n"
                     "filters: invert threshold blur\n";
        return 2;
    }

    imgfx::Image image = imgfx::read_pgm(std::cin);
    if (image.pixels.empty()) {
        std::cerr << "imgfx: not an ASCII PGM (P2) stream\n";
        return 1;
    }

    for (int i = 1; i < argc; ++i) {
        const std::string name = argv[i];
        if (name == "invert")
            image = imgfx::invert(image);
        else if (name == "threshold")
            image = imgfx::threshold(image);
        else if (name == "blur")
            image = imgfx::blur(image);
        else {
            std::cerr << "imgfx: unknown filter '" << name << "'\n";
            return 2;
        }
    }

    imgfx::write_pgm(image, std::cout);
    return 0;
}
