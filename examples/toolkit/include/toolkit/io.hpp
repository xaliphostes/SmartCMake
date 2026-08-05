#pragma once

#include <iosfwd>

#include "toolkit/mesh.hpp"

namespace toolkit {

/// Reads the subset of Wavefront OBJ this toolkit cares about: `v x y z`
/// vertices and `f a b c` triangles with 1-based indices. Unknown lines are
/// skipped rather than treated as an error.
Mesh read_obj(std::istream& in);

/// Writes the same subset back out.
void write_obj(std::ostream& out, const Mesh& mesh);

}  // namespace toolkit
