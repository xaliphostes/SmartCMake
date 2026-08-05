#include <gtest/gtest.h>

#include "toolkit/mesh.hpp"

namespace {

toolkit::Mesh unit_triangle()
{
    toolkit::Mesh mesh;
    mesh.vertices = {{0, 0, 0}, {1, 0, 0}, {0, 1, 0}};
    mesh.indices = {0, 1, 2};
    return mesh;
}

TEST(Mesh, CountsTrianglesFromIndices)
{
    EXPECT_EQ(unit_triangle().triangle_count(), 1u);
    EXPECT_EQ(toolkit::Mesh{}.triangle_count(), 0u);
}

TEST(Mesh, BoundsRejectsAnEmptyMesh)
{
    toolkit::Vec3 lo;
    toolkit::Vec3 hi;
    EXPECT_FALSE(toolkit::bounds(toolkit::Mesh{}, lo, hi));
}

TEST(Mesh, BoundsSpanEveryVertex)
{
    toolkit::Vec3 lo;
    toolkit::Vec3 hi;
    ASSERT_TRUE(toolkit::bounds(unit_triangle(), lo, hi));

    EXPECT_DOUBLE_EQ(lo.x, 0.0);
    EXPECT_DOUBLE_EQ(lo.y, 0.0);
    EXPECT_DOUBLE_EQ(hi.x, 1.0);
    EXPECT_DOUBLE_EQ(hi.y, 1.0);
}

}  // namespace
