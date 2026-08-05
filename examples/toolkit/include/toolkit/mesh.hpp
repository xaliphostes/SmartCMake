#pragma once

#include <cstddef>
#include <vector>

namespace toolkit {

struct Vec3 {
    double x = 0;
    double y = 0;
    double z = 0;
};

/// A triangle soup: `indices` holds three vertex indices per face.
struct Mesh {
    std::vector<Vec3> vertices;
    std::vector<int> indices;

    std::size_t triangle_count() const { return indices.size() / 3; }
};

/// Axis-aligned bounds. Returns false (and leaves lo/hi alone) for an empty mesh.
bool bounds(const Mesh& mesh, Vec3& lo, Vec3& hi);

}  // namespace toolkit
