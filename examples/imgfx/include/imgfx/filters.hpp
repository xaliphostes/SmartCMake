#pragma once

#include "imgfx/image.hpp"

namespace imgfx {

/// One filter per translation unit under filters/, each built into its own
/// static library from one row of the table in build.scmake.
Image invert(const Image& src);
Image threshold(const Image& src);
Image blur(const Image& src);

}  // namespace imgfx
