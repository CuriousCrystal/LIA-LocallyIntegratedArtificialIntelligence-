# Her icons

Drop the image you want her to wear into this folder. Any PNG, JPG, WebP,
GIF or BMP works; if there are several, a name starting with `lia` or
`tray_icon` wins. Nothing here is required -- with the folder empty she
draws her own cat face.

    python LIA\make_icon.py

turns your image into `lia.ico` -- one icon carrying 16, 32, 48, 64, 128 and
256px versions, transparent where your image is. The sizes are the point: the
tray renders 16px, the taskbar 32, the alt-tab switcher 256, and Windows
resamples a single-size icon per surface, which is what makes custom icons
look soft on high-DPI screens.

A non-square image is padded to a centred square on transparency by default;
`--crop` centre-crops it instead (right for photos, wrong for logos with
text). `--force` rebuilds even when the .ico is already current. She also
builds it herself at startup when your image is newer than the last build,
so dropping a file in and restarting is enough.

The original image is never modified -- the .ico is generated beside it, and
the drawn cat is still the fallback when this folder is empty.
