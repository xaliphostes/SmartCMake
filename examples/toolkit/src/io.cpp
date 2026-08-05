#include "toolkit/io.hpp"

#include <istream>
#include <ostream>
#include <sstream>
#include <string>

namespace toolkit {

Mesh read_obj(std::istream& in)
{
    Mesh mesh;
    std::string line;

    while (std::getline(in, line)) {
        std::istringstream fields(line);
        std::string tag;
        if (!(fields >> tag))
            continue;

        if (tag == "v") {
            Vec3 v;
            if (fields >> v.x >> v.y >> v.z)
                mesh.vertices.push_back(v);
        } else if (tag == "f") {
            int a = 0;
            int b = 0;
            int c = 0;
            if (fields >> a >> b >> c) {
                // OBJ indices are 1-based.
                mesh.indices.push_back(a - 1);
                mesh.indices.push_back(b - 1);
                mesh.indices.push_back(c - 1);
            }
        }
    }
    return mesh;
}

void write_obj(std::ostream& out, const Mesh& mesh)
{
    for (const Vec3& v : mesh.vertices)
        out << "v " << v.x << ' ' << v.y << ' ' << v.z << '\n';

    for (std::size_t i = 0; i + 2 < mesh.indices.size(); i += 3)
        out << "f " << mesh.indices[i] + 1 << ' ' << mesh.indices[i + 1] + 1 << ' '
            << mesh.indices[i + 2] + 1 << '\n';
}

}  // namespace toolkit
