#include "NifFile.hpp"
#include <cstdio>
#include <fstream>
#include <sstream>
using namespace nifly;
int main(int argc, char** argv) {
    NifFile nif;
    if (nif.Load(argv[1]) != 0) { printf("LOAD FAILED\n"); return 1; }
    if (!nif.IsValid()) { printf("INVALID\n"); return 1; }
    auto& hdr = nif.GetHeader();
    printf("version ok, blocks=%u user=%u bsver=%u\n", hdr.GetNumBlocks(), hdr.GetVersion().User(), hdr.GetVersion().Stream());
    for (auto* s : nif.GetShapes()) {
        printf("shape %s verts=%u tris=%u\n", s->name.get().c_str(), s->GetNumVertices(), s->GetNumTriangles());
        auto* sh = nif.GetShader(s);
        if (sh) { auto c = sh->GetEmissiveColor(); printf("  shader emissive %.2f %.2f %.2f mult %.2f tex=%s\n", c.r, c.g, c.b, sh->GetEmissiveMultiple(), sh->HasVertexColors() ? "vc" : "novc"); }
        auto* a = nif.GetAlphaProperty(s); printf("  alpha %s\n", a ? "yes" : "no");
        std::vector<Vector3> v; nif.GetVertsForShape(s, v);
        for (auto& p : v) printf("  v %.1f %.1f %.1f\n", p.x, p.y, p.z);
    }
    if (argc > 2) { nif.Save(argv[2]); printf("resaved\n"); }
    return 0;
}
