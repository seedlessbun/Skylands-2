#include "NifFile.hpp"
#include <cstdio>
#include <set>
using namespace nifly;
int main(int argc, char** argv) {
    NifFile nif;
    if (nif.Load(argv[1]) != 0) { printf("LOAD FAILED\n"); return 1; }
    if (!nif.IsValid()) { printf("INVALID\n"); return 1; }
    auto& hdr = nif.GetHeader();
    printf("blocks=%u bsver=%u\n", hdr.GetNumBlocks(), hdr.GetVersion().Stream());
    for (uint32_t i = 0; i < hdr.GetNumBlocks(); i++) printf("block %u %s\n", i, hdr.GetBlockTypeStringById(i).c_str());
    for (auto* s : nif.GetShapes()) {
        printf("shape %s verts=%u tris=%u\n", s->name.get().c_str(), s->GetNumVertices(), s->GetNumTriangles());
        std::vector<Vector3> v; nif.GetVertsForShape(s, v);
        float mn[3]={1e9,1e9,1e9}, mx[3]={-1e9,-1e9,-1e9};
        for (auto& p : v) { float a[3]={p.x,p.y,p.z}; for(int k=0;k<3;k++){ if(a[k]<mn[k])mn[k]=a[k]; if(a[k]>mx[k])mx[k]=a[k]; } }
        printf("  bounds %.2f %.2f %.2f .. %.2f %.2f %.2f\n", mn[0],mn[1],mn[2],mx[0],mx[1],mx[2]);
        const std::vector<Vector2>* uv = nif.GetUvsForShape(s); const std::vector<Vector3>* nn = nif.GetNormalsForShape(s); const std::vector<Vector3>* tt = nif.GetTangentsForShape(s);
        printf("  uvs=%zu normals=%zu tangents=%zu\n", uv?uv->size():0, nn?nn->size():0, tt?tt->size():0);
        for (uint32_t t = 0; t < 2; t++) { std::string tex; nif.GetTextureSlot(s, tex, t); printf("  tex%u=%s\n", t, tex.c_str()); }
        std::vector<Triangle> tris; s->GetTriangles(tris);
        uint32_t bad = 0; for (auto& t : tris) if (t.p1 >= v.size() || t.p2 >= v.size() || t.p3 >= v.size()) bad++;
        printf("  badtris=%u\n", bad);
        auto* sh = nif.GetShader(s);
        if (sh) { auto c = sh->GetEmissiveColor(); printf("  shader emissive %.2f %.2f %.2f mult %.2f %s\n", c.r, c.g, c.b, sh->GetEmissiveMultiple(), sh->HasVertexColors() ? "vc" : "novc"); }
        auto* a = nif.GetAlphaProperty(s); printf("  alpha %s\n", a ? "yes" : "no");
    }
    if (argc > 2) { nif.Save(argv[2]); printf("resaved\n"); }
    return 0;
}
