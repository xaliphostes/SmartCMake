#include <sstream>

#include <gtest/gtest.h>

#include "toolkit/io.hpp"

namespace {

TEST(Io, ReadsVerticesAndFaces)
{
    std::istringstream in("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n");
    const toolkit::Mesh mesh = toolkit::read_obj(in);

    EXPECT_EQ(mesh.vertices.size(), 3u);
    EXPECT_EQ(mesh.triangle_count(), 1u);
    // OBJ is 1-based on disk, 0-based in memory.
    EXPECT_EQ(mesh.indices, (std::vector<int>{0, 1, 2}));
}

TEST(Io, SkipsCommentsAndUnknownTags)
{
    std::istringstream in("# a comment\nvn 0 0 1\nv 2 3 4\n\n");
    const toolkit::Mesh mesh = toolkit::read_obj(in);

    ASSERT_EQ(mesh.vertices.size(), 1u);
    EXPECT_DOUBLE_EQ(mesh.vertices[0].x, 2.0);
    EXPECT_EQ(mesh.triangle_count(), 0u);
}

TEST(Io, RoundTripsThroughWriteAndRead)
{
    std::istringstream in("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n");
    const toolkit::Mesh original = toolkit::read_obj(in);

    std::ostringstream out;
    toolkit::write_obj(out, original);

    std::istringstream again(out.str());
    const toolkit::Mesh reloaded = toolkit::read_obj(again);

    EXPECT_EQ(reloaded.vertices.size(), original.vertices.size());
    EXPECT_EQ(reloaded.indices, original.indices);
}

}  // namespace
