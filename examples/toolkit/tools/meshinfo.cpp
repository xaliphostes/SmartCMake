#include <fstream>
#include <iostream>

#include "toolkit/io.hpp"
#include "toolkit/mesh.hpp"

int main(int argc, char** argv)
{
    if (argc != 2) {
        std::cerr << "usage: meshinfo <mesh.obj>\n";
        return 2;
    }

    std::ifstream in(argv[1]);
    if (!in) {
        std::cerr << "meshinfo: cannot open " << argv[1] << '\n';
        return 1;
    }

    const toolkit::Mesh mesh = toolkit::read_obj(in);
    std::cout << "vertices  " << mesh.vertices.size() << '\n'
              << "triangles " << mesh.triangle_count() << '\n';

    toolkit::Vec3 lo;
    toolkit::Vec3 hi;
    if (toolkit::bounds(mesh, lo, hi))
        std::cout << "bounds    (" << lo.x << ' ' << lo.y << ' ' << lo.z << ") .. ("
                  << hi.x << ' ' << hi.y << ' ' << hi.z << ")\n";

    return 0;
}
