# AudioHub ARM64 image build report — 2026-11-03

## Verified result

**Successful image build and checksum artifact delivery**, not hardware acceptance.

| Property | Verified value |
| --- | --- |
| Repository | `RIVANOXcom/rivanox-audiohub` |
| Build branch | `audiohub-preview-build` |
| Workflow run | [41732307538](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/41732307538) |
| Build source SHA | `230caaa9afd639718eb4025b4013808e3a4a8a30` |
| Pinned upstream pi-gen SHA | `c851f00178c64b87a86c06c2be216bd89d62e55b` |
| Runner | `ubuntu-24.04-arm`, native ARM64 |
| Build filename | `image_2026-11-03-AudioHub-Pi4-UNVERIFIED.img.xz` |
| Image build step | Success |
| SHA256SUMS generation and verification | Success |
| XZ integrity test | Success |
| Artifact upload | Success |
| Artifact ID | `13276489484` |
| Artifact archive size | 605,057,166 bytes |
| Retention | Seven days, unverified preview only |
| Physical Pi boot and audio | **Not tested** |
| Official GitHub Release | **Not published** |

GitHub Actions proves image creation and archive integrity, not functional audio routing, pairing security, first-boot commissioning or compatibility. The preview branch source of this particular artifact precedes the newer mobile status UI and other main improvements; do not describe this as the latest fully integrated product.

## Root cause resolved

Prior ARM64 [run 41730586400](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/41730586400) had already completed `pi-gen`, but failed when its post-build step wrote `SHA256SUMS.txt` into root-owned `.pi-gen-build/pi-gen/deploy`. The workflow now uses a writable `dist/` staging directory and verifies both SHA-256 and XZ before uploading the experimental artifact.

## Next build

Source SHA `51a6b0d3824e0c9cee0188a23ee27fc947c2dd8f` merges current main with the working ARM64 preview builder. [Run 41733550118](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/41733550118) builds a follow-up image with the localized read-only web-status service. Its status must be checked independently. It is also alpha and must not be promoted without the physical release gates.

## Workbench source-of-truth

Project `PJ2611-0001:R001`. Workbench requirement AH-006 ID 3272. Evidence record ID 2647 maps the verified image-build run and exact SHA. Current task remains in progress until the verified SD-card release conditions are met.

See [RELEASE-ACCEPTANCE.md](RELEASE-ACCEPTANCE.md) and [SECURITY-THREAT-MODEL.md](SECURITY-THREAT-MODEL.md).
