CMake is stuck with a mediocre programming language, has no loops, no data structures and no type.

Welcome **SmartCMake**: a source language that compiles *to* `CMakeLists.txt`.

```ts
record Filter {
    name: string
    sources: string[]
    defines: string[] = []
    test: bool = true
}

const FILTERS: Filter[] = [
    { name: "invert",    sources: ["filters/invert.cpp"] },
    { name: "threshold", sources: ["filters/threshold.cpp"],
      defines: ["IMGFX_THRESHOLD=96"], test: false },
]

for (f of FILTERS) {
    const lib = library(`imgfx_${f.name}`)(STATIC) {
        doc: `The ${f.name} filter.`
        sources: f.sources
        defines: f.defines
    }

    if (f.test) {                         // decided now — the arm just vanishes
        when (vars.IMGFX_BUILD_TESTS) {   // decided later, by CMake itself
            const suite = executable(`test_${f.name}`) {
                sources: [`tests/${f.name}_test.cpp`]
            }
            suite.link(lib, GTest.gtest_main)
            suite.discoverTests()
        }
    }
}
```

Records, so a typo in that table is a compile error instead of a link failure. `if` picks a branch **now** and only the winner is written out; `when` becomes a literal `if()/endif()` for CMake to decide on the user's machine. Two things that look the same in CMake and aren't.

It does **not** replace CMake — think TypeScript → JavaScript. You ship the generated `CMakeLists.txt`, your users install nothing, and you can throw the compiler away and still build. Full ecosystem compatibility, because the output *is* CMake.

Pure Python, no dependencies, MIT, v0.1 prototype.

What's the worst `CMakeLists.txt` you've had to maintain? I'll go first: the one that made me write this.

github.com/xaliphostes/SmartCMake

#cpp #cmake #buildsystems #devtools #opensource
