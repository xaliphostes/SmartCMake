#include "toolkit/mesh.hpp"

#include <algorithm>

namespace toolkit {

bool bounds(const Mesh& mesh, Vec3& lo, Vec3& hi)
{
    if (mesh.vertices.empty())
        return false;

    lo = hi = mesh.vertices.front();
    for (const Vec3& v : mesh.vertices) {
        lo.x = std::min(lo.x, v.x);
        lo.y = std::min(lo.y, v.y);
        lo.z = std::min(lo.z, v.z);
        hi.x = std::max(hi.x, v.x);
        hi.y = std::max(hi.y, v.y);
        hi.z = std::max(hi.z, v.z);
    }
    return true;
}

}  // namespace toolkit
