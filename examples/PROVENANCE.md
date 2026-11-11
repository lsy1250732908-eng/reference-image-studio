# Example image provenance

Both example PNG files depict a fictional, AI-generated illustrated woman. They are not uploaded personal photographs. They contain no EXIF or embedded ComfyUI metadata.

- `reference.png` is pixel-identical to a previously generated SD 1.5 output. The original successful execution record contains a text-to-image workflow (EmptyLatentImage, CLIPTextEncode, KSampler, VAEDecode, SaveImage), with this positive prompt: `watercolor illustration, portrait of an adult woman, short black hair, round glasses, blue coat, gentle smile, looking at the viewer, leafy garden background, soft morning light, pastel colors`. Pixel equality with that original output was checked before publication.
- `generated.png` was produced by the real end-to-end integration test in this project, using that synthetic reference. The caption, complete prompt, model settings and timing are recorded in `test-report.json`.
- Both images were visually reviewed before publication. They show only a stylized portrait with glasses and leaves.

SHA-256:

```text
044a187960d3ade8ec8251771501fd3de91430fe034dd2b7a1c0942929f3c404  reference.png
a7f0fb0b6069dc615a46182834cd0607888ee724323d86d59a3b550eb7a1ffc5  generated.png
```
