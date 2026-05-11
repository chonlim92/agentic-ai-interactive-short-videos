"""Process logos: extract icon, beautify all variants, generate favicon."""
from PIL import Image
import numpy as np
from pathlib import Path

LOGO_DIR = Path("site/logo")

def remove_white_bg(img: Image.Image, threshold=230, feather=50) -> Image.Image:
    """Remove white background with smooth anti-aliased edges."""
    data = np.array(img.convert("RGBA"))
    r, g, b, a = data[:,:,0], data[:,:,1], data[:,:,2], data[:,:,3]
    
    # Fully transparent for white/near-white
    white_mask = (r > threshold) & (g > threshold) & (b > threshold)
    data[white_mask] = [255, 255, 255, 0]
    
    # Anti-alias zone for smooth edges
    lower = threshold - feather
    light_mask = (r > lower) & (g > lower) & (b > lower) & ~white_mask
    if np.any(light_mask):
        brightness = (r[light_mask].astype(float) + g[light_mask].astype(float) + b[light_mask].astype(float)) / 3
        alpha_vals = np.clip(((threshold - brightness) / feather * 255), 0, 255).astype(np.uint8)
        data[light_mask, 3] = alpha_vals
    
    return Image.fromarray(data)


def find_content_bbox(img: Image.Image, min_alpha=10):
    """Find bounding box of non-transparent content."""
    alpha = np.array(img)[:,:,3]
    rows = np.any(alpha > min_alpha, axis=1)
    cols = np.any(alpha > min_alpha, axis=0)
    if not rows.any() or not cols.any():
        return (0, 0, img.width, img.height)
    rmin, rmax = np.where(rows)[0][[0, -1]]
    cmin, cmax = np.where(cols)[0][[0, -1]]
    return (cmin, rmin, cmax + 1, rmax + 1)


def find_icon_bottom(img: Image.Image) -> int:
    """Find where the icon ends (gap between icon and text) in the normal logo."""
    alpha = np.array(img)[:,:,3]
    h = alpha.shape[0]
    
    # Look for a horizontal gap (row with very few non-transparent pixels)
    # Start from middle and scan downward
    row_densities = []
    for y in range(h):
        density = np.sum(alpha[y,:] > 10)
        row_densities.append((y, density))
    
    # Find the gap between icon and text (a region of very low density)
    # The icon is roughly the top 60%, text is bottom 40%
    mid = h // 2
    min_density = 9999
    gap_y = mid
    for y in range(mid, int(h * 0.85)):
        density = row_densities[y][1]
        if density < min_density:
            min_density = density
            gap_y = y
    
    return gap_y


def crop_and_pad(img: Image.Image, padding=20) -> Image.Image:
    """Crop to content with padding, make square."""
    bbox = find_content_bbox(img)
    cropped = img.crop(bbox)
    
    # Add padding
    w, h = cropped.size
    new_size = max(w, h) + padding * 2
    result = Image.new("RGBA", (new_size, new_size), (0, 0, 0, 0))
    offset_x = (new_size - w) // 2
    offset_y = (new_size - h) // 2
    result.paste(cropped, (offset_x, offset_y), cropped)
    return result


def main():
    print("=== Processing Logos ===\n")
    
    # 1. Load original logos (re-process from originals to get best quality)
    normal_path = LOGO_DIR / "storysmithai_logo_normal.png"
    horiz_path = LOGO_DIR / "storysmithai_logo_horizontal.png"
    
    normal = Image.open(normal_path).convert("RGBA")
    horiz = Image.open(horiz_path).convert("RGBA")
    print(f"Normal: {normal.size}")
    print(f"Horizontal: {horiz.size}")
    
    # 2. Find icon boundary in normal logo
    gap_y = find_icon_bottom(normal)
    print(f"Icon/text gap at row: {gap_y}")
    
    # 3. Extract icon-only (everything above the gap)
    icon_region = normal.crop((0, 0, normal.width, gap_y))
    icon_clean = remove_white_bg(icon_region)
    icon_final = crop_and_pad(icon_clean, padding=10)
    icon_path = LOGO_DIR / "storysmithai_logo_icon.png"
    icon_final.save(icon_path, "PNG")
    print(f"Icon extracted: {icon_final.size} -> {icon_path}")
    
    # 4. Beautify normal logo (re-process with better params)
    normal_clean = remove_white_bg(normal)
    normal_cropped = crop_and_pad(normal_clean, padding=15)
    normal_cropped.save(normal_path, "PNG")
    print(f"Normal beautified: {normal_cropped.size}")
    
    # 5. Beautify horizontal logo
    horiz_clean = remove_white_bg(horiz)
    horiz_bbox = find_content_bbox(horiz_clean)
    horiz_cropped = horiz_clean.crop(horiz_bbox)
    # Add horizontal padding (not square)
    pad = 15
    w, h = horiz_cropped.size
    horiz_padded = Image.new("RGBA", (w + pad*2, h + pad*2), (0, 0, 0, 0))
    horiz_padded.paste(horiz_cropped, (pad, pad), horiz_cropped)
    horiz_padded.save(horiz_path, "PNG")
    print(f"Horizontal beautified: {horiz_padded.size}")
    
    # 6. Generate favicon variants from icon
    # Standard favicon sizes
    favicon_dir = Path("site/public")
    favicon_dir.mkdir(parents=True, exist_ok=True)
    
    # ICO with multiple sizes
    ico_sizes = [16, 32, 48]
    ico_images = []
    for size in ico_sizes:
        resized = icon_final.resize((size, size), Image.LANCZOS)
        ico_images.append(resized)
    
    ico_path = favicon_dir / "favicon.ico"
    ico_images[0].save(ico_path, format="ICO", sizes=[(s, s) for s in ico_sizes], append_images=ico_images[1:])
    print(f"Favicon ICO: {ico_path} ({ico_sizes})")
    
    # apple-touch-icon (180x180)
    apple_icon = icon_final.resize((180, 180), Image.LANCZOS)
    apple_path = favicon_dir / "apple-touch-icon.png"
    apple_icon.save(apple_path, "PNG")
    print(f"Apple touch icon: {apple_path}")
    
    # favicon-32x32 and favicon-16x16
    for size in [32, 16]:
        fav = icon_final.resize((size, size), Image.LANCZOS)
        fav_path = favicon_dir / f"favicon-{size}x{size}.png"
        fav.save(fav_path, "PNG")
        print(f"Favicon {size}x{size}: {fav_path}")
    
    # 192x192 and 512x512 for PWA
    for size in [192, 512]:
        pwa = icon_final.resize((size, size), Image.LANCZOS)
        pwa_path = favicon_dir / f"icon-{size}x{size}.png"
        pwa.save(pwa_path, "PNG")
        print(f"PWA icon {size}x{size}: {pwa_path}")
    
    print("\n=== Done ===")


if __name__ == "__main__":
    main()
