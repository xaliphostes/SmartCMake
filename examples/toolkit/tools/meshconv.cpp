#include <fstream>
#include <iostream>

#include "toolkit/io.hpp"

int main(int argc, char** argv)
{
    if (argc != 2) {
        std::cerr << "usage: meshconv <mesh.obj>   # normalized OBJ on stdout\n";
        return 2;
    }

    std::ifstream in(argv[1]);
    if (!in) {
        std::cerr << "meshconv: cannot open " << argv[1] << '\n';
        return 1;
    }

    toolkit::write_obj(std::cout, toolkit::read_obj(in));
    return 0;
}
