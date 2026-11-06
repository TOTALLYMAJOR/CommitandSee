# GitHub social preview

The owner selected a product-first image with CommitandSee's name, a short
headline, and a labeled synthetic dashboard crop. The selected production method
is local HTML/CSS composition and an actual browser capture of the bundled demo.
No private workspace screenshot, generated artwork, external font, or stock asset
is used. This file and renderer have no application runtime cost.

The upload asset is [images/social-preview.png](images/social-preview.png).
Its source is [social-preview.html](social-preview.html); the dashboard crop is
generated from the current `demo.html`. To reproduce with an existing Playwright
and Chromium installation:

```bash
python3 git_dashboard.py demo --output demo.html
node docs/render-social-preview.cjs
```

Use `PLAYWRIGHT_MODULE` and `CHROMIUM_EXECUTABLE` if those development tools are
installed outside the repository. The renderer blocks HTTP(S) requests and uses
only bundled synthetic data. It checks the output is 1280×640 and under 1 MB.

Repository administrators can open
[Settings → Social preview](https://github.com/TOTALLYMAJOR/CommitandSee/settings),
choose **Edit → Upload an image**, and select `social-preview.png`. GitHub's
[social preview documentation](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/customizing-your-repositorys-social-media-preview)
describes the supported dimensions and formats. Committing this asset does not
set the repository's sharing image; verify the image in Settings after upload.
