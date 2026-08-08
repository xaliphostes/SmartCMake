#include <gtest/gtest.h>

#include "imgfx/filters.hpp"

TEST(Invert, MapsEachPixelToItsComplement)
{
    imgfx::Image image(2, 1);
    image.at(0, 0) = 0;
    image.at(1, 0) = 200;

    const imgfx::Image out = imgfx::invert(image);
    EXPECT_EQ(out.at(0, 0), 255);
    EXPECT_EQ(out.at(1, 0), 55);
}

TEST(Invert, LeavesTheGeometryAlone)
{
    const imgfx::Image out = imgfx::invert(imgfx::Image(4, 3));
    EXPECT_EQ(out.width, 4);
    EXPECT_EQ(out.height, 3);
}
