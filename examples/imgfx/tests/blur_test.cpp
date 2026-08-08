#include <gtest/gtest.h>

#include "imgfx/filters.hpp"

TEST(Blur, AveragesTheNeighbourhood)
{
    imgfx::Image image(3, 3);
    image.at(1, 1) = 90;

    const imgfx::Image out = imgfx::blur(image);
    EXPECT_EQ(out.at(1, 1), 10);  // full 9-pixel window: 90 / 9
    EXPECT_EQ(out.at(0, 0), 22);  // corner window is 4 pixels: 90 / 4
}

TEST(Blur, LeavesAFlatImageFlat)
{
    imgfx::Image image(4, 4);
    for (auto& pixel : image.pixels)
        pixel = 128;

    const imgfx::Image out = imgfx::blur(image);
    for (const auto pixel : out.pixels)
        EXPECT_EQ(pixel, 128);
}
