import os
import io
from PIL import Image, ImageDraw, ExifTags

def create_fixtures(output_dir):
    os.makedirs(output_dir, exist_ok=True)
    
    # 1. Single portrait (800x1000)
    img1 = Image.new("RGB", (800, 1000), color=(220, 230, 242))
    draw1 = ImageDraw.Draw(img1)
    # Draw oval head and shoulders
    draw1.ellipse([300, 250, 500, 500], fill=(245, 205, 180), outline=(100, 100, 100), width=3)
    draw1.rectangle([200, 500, 600, 950], fill=(70, 90, 130))
    path1 = os.path.join(output_dir, "single_portrait.jpg")
    img1.save(path1, "JPEG", quality=90)
    
    # 2. Crowded group with 100+ faces (3200x2000)
    img2 = Image.new("RGB", (3200, 2000), color=(240, 240, 245))
    draw2 = ImageDraw.Draw(img2)
    # Draw 10 rows x 11 cols = 110 faces
    cols, rows = 11, 10
    step_x = 3200 / (cols + 1)
    step_y = 2000 / (rows + 1)
    for r in range(rows):
        for c in range(cols):
            cx = (c + 1) * step_x
            cy = (r + 1) * step_y
            draw2.ellipse([cx - 40, cy - 40, cx + 40, cy + 40], fill=(235, 195, 175), outline=(50, 50, 50), width=2)
    path2 = os.path.join(output_dir, "crowded_group_100.jpg")
    img2.save(path2, "JPEG", quality=85)
    
    # 3. Small image (64x64)
    img3 = Image.new("RGB", (64, 64), color=(200, 220, 200))
    draw3 = ImageDraw.Draw(img3)
    draw3.ellipse([16, 16, 48, 48], fill=(240, 200, 170))
    path3 = os.path.join(output_dir, "small_image.jpg")
    img3.save(path3, "JPEG", quality=90)
    
    # 4. Large image (4000x3000)
    img4 = Image.new("RGB", (4000, 3000), color=(210, 215, 225))
    path4 = os.path.join(output_dir, "large_image.jpg")
    img4.save(path4, "JPEG", quality=85)
    
    # 5. Rotated EXIF photo (800x600, orientation 6 = 90 deg CW)
    img5 = Image.new("RGB", (800, 600), color=(250, 230, 200))
    draw5 = ImageDraw.Draw(img5)
    draw5.rectangle([50, 50, 750, 200], fill=(180, 80, 80)) # Distinct asymmetry
    exif5 = img5.getexif()
    # 0x0112 is Orientation tag
    exif5[0x0112] = 6
    path5 = os.path.join(output_dir, "rotated_exif.jpg")
    img5.save(path5, "JPEG", exif=exif5)
    
    # 6. PNG transparency (500x500 RGBA)
    img6 = Image.new("RGBA", (500, 500), color=(0, 0, 0, 0))
    draw6 = ImageDraw.Draw(img6)
    draw6.ellipse([100, 100, 400, 400], fill=(100, 150, 220, 200), outline=(20, 40, 80, 255), width=4)
    path6 = os.path.join(output_dir, "transparent_alpha.png")
    img6.save(path6, "PNG")
    
    # 7. WebP image (600x600)
    img7 = Image.new("RGB", (600, 600), color=(230, 245, 230))
    draw7 = ImageDraw.Draw(img7)
    draw7.ellipse([200, 200, 400, 400], fill=(240, 200, 180))
    path7 = os.path.join(output_dir, "lossy_web.webp")
    img7.save(path7, "WEBP", quality=90)
    
    # 8. Multilingual & accented names (800x600)
    img8 = Image.new("RGB", (800, 600), color=(245, 240, 235))
    draw8 = ImageDraw.Draw(img8)
    draw8.ellipse([150, 150, 300, 300], fill=(230, 190, 160))
    draw8.ellipse([500, 150, 650, 300], fill=(210, 170, 140))
    path8 = os.path.join(output_dir, "multilingual_names.jpg")
    img8.save(path8, "JPEG", quality=90)
    
    # 9. Empty description (800x600)
    img9 = Image.new("RGB", (800, 600), color=(235, 235, 240))
    path9 = os.path.join(output_dir, "empty_description.jpg")
    img9.save(path9, "JPEG", quality=90)
    
    # 10. Malformed metadata JPEG
    img10 = Image.new("RGB", (400, 400), color=(240, 220, 220))
    path10 = os.path.join(output_dir, "malformed_metadata.jpg")
    # Save with invalid XMP packet
    img10.save(path10, "JPEG", xmp=b"<x:xmpmeta>INVALID UNCLOSED XML")

    print(f"Fixtures successfully created in: {output_dir}")

if __name__ == "__main__":
    target_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "fixtures"))
    create_fixtures(target_dir)
