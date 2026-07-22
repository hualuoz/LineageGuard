# LineageGuard demo video

This directory contains the reproducible Remotion source for the 66-second LineageGuard product demo.
The `public/live-console-*.png` frames were captured from the functioning local FastAPI app
while changing the SQL and rerunning the merge gate; the video uses them as a real execution
sequence alongside the explanatory animation.

```bash
npm install
npm run lint
npm run render
```

The rendered H.264 video is written to `out/lineageguard-demo.mp4`. Rendered files are intentionally ignored by Git.
