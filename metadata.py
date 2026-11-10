try:
    import defusedxml.ElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET
import html
import re
import os
import shutil
from PIL import Image

# Namespace registry for ElementTree to use correct prefixes
NAMESPACES = {
    'x': 'adobe:ns:meta/',
    'rdf': 'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
    'xmp': 'http://ns.adobe.com/xap/1.0/',
    'mwg-rs': 'http://www.metadataworkinggroup.org/schemas/regions/',
    'stDim': 'http://ns.adobe.com/xmp/sType/Dimensions#',
    'stArea': 'http://ns.adobe.com/xmp/sType/Area#',
    'MP': 'http://ns.microsoft.com/photo/1.2/',
    'MPRI': 'http://ns.microsoft.com/photo/1.2/t/RegionInfo#',
    'MPReg': 'http://ns.microsoft.com/photo/1.2/t/Region#',
    'dc': 'http://purl.org/dc/elements/1.1/'
}

for prefix, uri in NAMESPACES.items():
    ET.register_namespace(prefix, uri)

def sort_faces_spatial(faces):
    """
    Sorts face tags into natural visual reading order:
    Groups faces into horizontal rows/layers from Top to Bottom,
    and sorts Left to Right within each row.
    """
    if not faces:
        return []
        
    faces_copy = list(faces)
    avg_h = sum(f.get('h', 0.1) for f in faces_copy) / len(faces_copy)
    row_threshold = max(0.035, avg_h * 0.60)
    
    faces_copy.sort(key=lambda f: f['y'])
    
    rows = []
    for f in faces_copy:
        placed = False
        for row in rows:
            avg_y = sum(item['y'] for item in row) / len(row)
            if abs(f['y'] - avg_y) <= row_threshold:
                row.append(f)
                placed = True
                break
        if not placed:
            rows.append([f])
            
    rows.sort(key=lambda r: sum(item['y'] for item in r) / len(r))
    
    sorted_result = []
    for row in rows:
        row.sort(key=lambda item: item['x'])
        sorted_result.extend(row)
        
    return sorted_result

def read_photo_metadata(image_path):
    """
    Reads face regions and description from EXIF and XMP metadata.
    Returns a dict: {
        'description': '...',
        'tags': [ {'name': '...', 'x': 0.5, 'y': 0.5, 'w': 0.1, 'h': 0.1}, ... ]
    }
    """
    metadata = {
        'description': '',
        'tags': []
    }
    
    try:
        with Image.open(image_path) as img:
            # 1. Read EXIF Description (Tag 270)
            exif = img.getexif()
            if exif and 270 in exif:
                metadata['description'] = str(exif[270]).strip()
                
            # 2. Read XMP bytes
            xmp_bytes = img.info.get("xmp")
            if not xmp_bytes:
                if metadata['tags']:
                    metadata['tags'] = sort_faces_spatial(metadata['tags'])
                return metadata
            
            try:
                xmp_str = xmp_bytes.decode('utf-8', errors='ignore')
                # Extract xml block cleanly
                match = re.search(r'(<x:xmpmeta.*?</x:xmpmeta>)', xmp_str, re.DOTALL)
                if match:
                    root = ET.fromstring(match.group(1))
                else:
                    root = ET.fromstring(xmp_str)
            except Exception as e:
                print(f"Warning: Failed to parse XMP XML in {image_path}: {e}")
                if metadata['tags']:
                    metadata['tags'] = sort_faces_spatial(metadata['tags'])
                return metadata

            # 3. Read general description from XMP dc:description if not found in EXIF
            if not metadata['description']:
                dc_desc = root.find('.//{http://purl.org/dc/elements/1.1/}description')
                if dc_desc is not None:
                    li = dc_desc.find('.//{http://www.w3.org/1999/02/22-rdf-syntax-ns#}li')
                    if li is not None and li.text:
                        metadata['description'] = li.text.strip()

            # 4. Read face regions
            mwg_regions = root.find('.//{http://www.metadataworkinggroup.org/schemas/regions/}Regions')
            if mwg_regions is not None:
                region_list = mwg_regions.find('.//{http://www.metadataworkinggroup.org/schemas/regions/}RegionList')
                if region_list is not None:
                    for li in region_list.findall('.//{http://www.w3.org/1999/02/22-rdf-syntax-ns#}li'):
                        name_elem = li.find('{http://www.metadataworkinggroup.org/schemas/regions/}Name')
                        name = (name_elem.text or "") if name_elem is not None else ""
                        
                        area_elem = li.find('{http://www.metadataworkinggroup.org/schemas/regions/}Area')
                        if area_elem is not None:
                            x = float(area_elem.get('{http://ns.adobe.com/xmp/sType/Area#}x', 0.0))
                            y = float(area_elem.get('{http://ns.adobe.com/xmp/sType/Area#}y', 0.0))
                            w = float(area_elem.get('{http://ns.adobe.com/xmp/sType/Area#}w', 0.0))
                            h = float(area_elem.get('{http://ns.adobe.com/xmp/sType/Area#}h', 0.0))
                            metadata['tags'].append({'name': name, 'x': x, 'y': y, 'w': w, 'h': h})
                    if metadata['tags']:
                        metadata['tags'] = sort_faces_spatial(metadata['tags'])
                        return metadata

            # If no MWG regions, try Microsoft RegionInfo
            mp_region_info = root.find('.//{http://ns.microsoft.com/photo/1.2/}RegionInfo')
            if mp_region_info is not None:
                regions = mp_region_info.find('.//{http://ns.microsoft.com/photo/1.2/t/RegionInfo#}Regions')
                if regions is not None:
                    for li in regions.findall('.//{http://www.w3.org/1999/02/22-rdf-syntax-ns#}li'):
                        desc_el = li.find('{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Description')
                        source = desc_el if desc_el is not None else li
                        
                        name = source.get('{http://ns.microsoft.com/photo/1.2/t/Region#}PersonDisplayName') or ""
                        rect_str = source.get('{http://ns.microsoft.com/photo/1.2/t/Region#}Rectangle') or ""
                        if rect_str:
                            try:
                                left, top, w, h = map(float, rect_str.split(','))
                                x = left + w / 2.0
                                y = top + h / 2.0
                                metadata['tags'].append({'name': name, 'x': x, 'y': y, 'w': w, 'h': h})
                            except Exception as e:
                                print(f"Error parsing Microsoft region rectangle: {rect_str}: {e}")
    except Exception as e:
        print(f"Error reading metadata from {image_path}: {e}")
        
    if metadata['tags']:
        metadata['tags'] = sort_faces_spatial(metadata['tags'])
        
    return metadata

def write_photo_metadata(image_path, tags, description, original_path=None):
    """
    Writes face regions (MWG & Microsoft format) and description (EXIF & XMP) back to the target image path.
    Supports JPEG, PNG, and WebP formats. Handles conversions from original_path.
    """
    load_path = original_path if original_path else image_path
    temp_path = image_path + ".tmp"
    
    try:
        # Load the original/source image
        with Image.open(load_path) as img:
            width, height = img.size
            existing_xmp_bytes = img.info.get("xmp")
            exif = img.getexif() or Image.Exif()
            
            # Determine target format from extension
            ext = os.path.splitext(image_path)[1].lower()
            if ext in ('.jpg', '.jpeg'):
                fmt = 'JPEG'
            elif ext == '.png':
                fmt = 'PNG'
            elif ext == '.webp':
                fmt = 'WEBP'
            else:
                fmt = img.format if img.format else 'JPEG'
                
            # Build saving parameters
            save_params = {
                'format': fmt
            }
            
            # Update EXIF description (tag 270)
            if description:
                exif[270] = description.strip()
            else:
                if 270 in exif:
                    del exif[270]
                    
            if fmt in ('JPEG', 'WEBP', 'PNG'):
                save_params['exif'] = exif
                
            # Quality & subsampling settings
            if fmt == 'JPEG':
                if 'quality' in img.info:
                    save_params['quality'] = img.info['quality']
                else:
                    save_params['quality'] = 95
                if 'subsampling' in img.info:
                    save_params['subsampling'] = img.info['subsampling']
            elif fmt == 'WEBP':
                save_params['quality'] = 95
            
            # Parse or create new XMP structure
            root = None
            if existing_xmp_bytes:
                try:
                    xmp_str = existing_xmp_bytes.decode('utf-8', errors='ignore')
                    match = re.search(r'(<x:xmpmeta.*?</x:xmpmeta>)', xmp_str, re.DOTALL)
                    if match:
                        root = ET.fromstring(match.group(1))
                    else:
                        root = ET.fromstring(xmp_str)
                except Exception as e:
                    print(f"Warning: Failed to parse existing XMP, recreating. Error: {e}")
                    root = None
            
            if root is None:
                root = ET.Element('{adobe:ns:meta/}xmpmeta', {'{http://www.w3.org/1999/02/22-rdf-syntax-ns#}about': ''})
                rdf = ET.SubElement(root, '{http://www.w3.org/1999/02/22-rdf-syntax-ns#}RDF')
                desc = ET.SubElement(rdf, '{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Description', {
                    '{http://www.w3.org/1999/02/22-rdf-syntax-ns#}about': ''
                })
            else:
                rdf = root.find('.//{http://www.w3.org/1999/02/22-rdf-syntax-ns#}RDF')
                if rdf is None:
                    rdf = ET.SubElement(root, '{http://www.w3.org/1999/02/22-rdf-syntax-ns#}RDF')
                desc = rdf.find('.//{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Description')
                if desc is None:
                    desc = ET.SubElement(rdf, '{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Description', {
                        '{http://www.w3.org/1999/02/22-rdf-syntax-ns#}about': ''
                    })
 
            # Clean existing MWG Regions, Microsoft RegionInfo, and dc:description
            for child in list(desc):
                if child.tag in (
                    '{http://www.metadataworkinggroup.org/schemas/regions/}Regions',
                    '{http://ns.microsoft.com/photo/1.2/}RegionInfo',
                    '{http://purl.org/dc/elements/1.1/}description'
                ):
                    desc.remove(child)
 
            # Update XMP dc:description
            if description:
                dc_desc = ET.SubElement(desc, '{http://purl.org/dc/elements/1.1/}description')
                alt = ET.SubElement(dc_desc, '{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Alt')
                li = ET.SubElement(alt, '{http://www.w3.org/1999/02/22-rdf-syntax-ns#}li', {
                    '{http://www.w3.org/XML/1998/namespace}lang': 'x-default'
                })
                li.text = description.strip()
 
            if tags:
                # Add MWG Regions
                mwg_regions = ET.SubElement(desc, '{http://www.metadataworkinggroup.org/schemas/regions/}Regions', {
                    '{http://www.w3.org/1999/02/22-rdf-syntax-ns#}parseType': 'Resource'
                })
                ET.SubElement(mwg_regions, '{http://www.metadataworkinggroup.org/schemas/regions/}AppliedToDimensions', {
                    '{http://ns.adobe.com/xmp/sType/Dimensions#}w': str(width),
                    '{http://ns.adobe.com/xmp/sType/Dimensions#}h': str(height),
                    '{http://ns.adobe.com/xmp/sType/Dimensions#}unit': 'pixel'
                })
                region_list = ET.SubElement(mwg_regions, '{http://www.metadataworkinggroup.org/schemas/regions/}RegionList')
                bag = ET.SubElement(region_list, '{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Bag')
 
                for t in tags:
                    li = ET.SubElement(bag, '{http://www.w3.org/1999/02/22-rdf-syntax-ns#}li', {
                        '{http://www.w3.org/1999/02/22-rdf-syntax-ns#}parseType': 'Resource'
                    })
                    ET.SubElement(li, '{http://www.metadataworkinggroup.org/schemas/regions/}Area', {
                        '{http://ns.adobe.com/xmp/sType/Area#}x': f"{t['x']:.6f}",
                        '{http://ns.adobe.com/xmp/sType/Area#}y': f"{t['y']:.6f}",
                        '{http://ns.adobe.com/xmp/sType/Area#}w': f"{t['w']:.6f}",
                        '{http://ns.adobe.com/xmp/sType/Area#}h': f"{t['h']:.6f}",
                        '{http://ns.adobe.com/xmp/sType/Area#}unit': 'normalized'
                    })
                    name_elem = ET.SubElement(li, '{http://www.metadataworkinggroup.org/schemas/regions/}Name')
                    name_elem.text = str(t['name']) if t['name'] is not None else ""
                    type_elem = ET.SubElement(li, '{http://www.metadataworkinggroup.org/schemas/regions/}Type')
                    type_elem.text = 'Face'
 
                # Add Microsoft Region Info
                mp_region_info = ET.SubElement(desc, '{http://ns.microsoft.com/photo/1.2/}RegionInfo', {
                    '{http://www.w3.org/1999/02/22-rdf-syntax-ns#}parseType': 'Resource'
                })
                mp_regions = ET.SubElement(mp_region_info, '{http://ns.microsoft.com/photo/1.2/t/RegionInfo#}Regions')
                mp_bag = ET.SubElement(mp_regions, '{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Bag')
 
                for t in tags:
                    left = max(0.0, min(1.0, t['x'] - t['w'] / 2.0))
                    top = max(0.0, min(1.0, t['y'] - t['h'] / 2.0))
                    w = max(0.0, min(1.0 - left, t['w']))
                    h = max(0.0, min(1.0 - top, t['h']))
                    rect_str = f"{left:.6f}, {top:.6f}, {w:.6f}, {h:.6f}"
                    
                    li = ET.SubElement(mp_bag, '{http://www.w3.org/1999/02/22-rdf-syntax-ns#}li')
                    ET.SubElement(li, '{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Description', {
                        '{http://ns.microsoft.com/photo/1.2/t/Region#}Rectangle': rect_str,
                        '{http://ns.microsoft.com/photo/1.2/t/Region#}PersonDisplayName': str(t['name']) if t['name'] is not None else ""
                    })
 
            # Serialize XMP block
            xml_str = ET.tostring(root, encoding='utf-8').decode('utf-8')
            packet = f'<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>\n{xml_str}\n<?xpacket end="w"?>'
            packet_bytes = packet.encode('utf-8')
            
            # Prepare image to save (convert to RGB if saving to JPEG and mode is RGBA/transparency)
            save_img = img
            if fmt == 'JPEG' and img.mode in ('RGBA', 'LA', 'P'):
                save_img = img.convert('RGB')
                
            # Inject XMP block based on format
            if fmt == 'PNG':
                from PIL.PngImagePlugin import PngInfo
                png_info = PngInfo()
                png_info.add_itxt("XML:com.adobe.xmp", packet)
                save_params['pnginfo'] = png_info
            else:
                save_params['xmp'] = packet_bytes
            
            # Save the image to the temp path
            save_img.save(temp_path, **save_params)
            
        # Safely replace target path with newly saved file using atomic replacement
        if os.path.exists(temp_path):
            backup_path = image_path + ".bak"
            has_backup = False
            try:
                if os.path.exists(image_path):
                    try:
                        shutil.copy2(image_path, backup_path)
                        has_backup = True
                    except Exception:
                        pass
                
                os.replace(temp_path, image_path)
                
                if has_backup and os.path.exists(backup_path):
                    try:
                        os.remove(backup_path)
                    except Exception:
                        pass
                return True
            except Exception as replace_err:
                if has_backup and not os.path.exists(image_path) and os.path.exists(backup_path):
                    try:
                        os.replace(backup_path, image_path)
                    except Exception:
                        pass
                raise replace_err
            finally:
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass
    except Exception as e:
        print(f"Error saving metadata for {image_path}: {e}")
        # Clean up temp file if exists
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except:
            pass
        return False

def resolve_font_files_for_family(font_family: str = "Segoe UI"):
    """
    Returns prioritized font file paths for the requested font family with
    tested Windows system fallbacks and Persian/Arabic script coverage.
    Supported choices: 'Segoe UI' (default), 'Tahoma', 'Arial'.
    """
    family = (font_family or "Segoe UI").strip().lower()
    if "tahoma" in family:
        return [
            "C:\\Windows\\Fonts\\tahomabd.ttf",
            "C:\\Windows\\Fonts\\tahoma.ttf",
            "tahomabd.ttf",
            "tahoma.ttf",
            "C:\\Windows\\Fonts\\segoeuib.ttf",
            "C:\\Windows\\Fonts\\segoeui.ttf",
            "C:\\Windows\\Fonts\\arialbd.ttf",
            "C:\\Windows\\Fonts\\arial.ttf",
        ]
    elif "arial" in family:
        return [
            "C:\\Windows\\Fonts\\arialbd.ttf",
            "C:\\Windows\\Fonts\\arial.ttf",
            "arialbd.ttf",
            "arial.ttf",
            "C:\\Windows\\Fonts\\segoeuib.ttf",
            "C:\\Windows\\Fonts\\segoeui.ttf",
            "C:\\Windows\\Fonts\\tahoma.ttf",
        ]
    else:  # Segoe UI (default)
        return [
            "C:\\Windows\\Fonts\\segoeuib.ttf",
            "C:\\Windows\\Fonts\\segoeui.ttf",
            "segoeuib.ttf",
            "segoeui.ttf",
            "C:\\Windows\\Fonts\\tahomabd.ttf",
            "C:\\Windows\\Fonts\\tahoma.ttf",
            "C:\\Windows\\Fonts\\arialbd.ttf",
            "C:\\Windows\\Fonts\\arial.ttf",
        ]


def write_interactive_html(image_path, tags, description, color_style=None, font_size_style=None, font_family="Segoe UI", source_image=None):
    """
    Exports a standalone interactive HTML file packaging the image (in Base64)
    with CSS-styled hover overlays and tooltips.
    """
    import base64
    import os
    import io
    try:
        # Get custom styling or defaults
        color_hex = color_style.get("hex", "#2563eb") if color_style else "#2563eb"
        hover_hex = color_style.get("hex", "#38bdf8") if color_style else "#38bdf8"
        bg_hover = color_style.get("hover", "rgba(56, 189, 248, 0.15)") if color_style else "rgba(56, 189, 248, 0.15)"
        font_size_px = font_size_style.get("px", 13) if font_size_style else 13
        
        # Convert hex to rgba for box-shadow to support transparency
        shadow_rgba = "rgba(56, 189, 248, 0.6)"
        if color_style:
            r, g, b = color_style.get("rgb", (59, 130, 246))
            shadow_rgba = f"rgba({r}, {g}, {b}, 0.6)"

        # Determine mime-type from extension
        ext = os.path.splitext(image_path)[1].lower() if isinstance(image_path, str) else ".jpg"
        mime_type = "image/jpeg"
        if ext == ".png":
            mime_type = "image/png"
        elif ext == ".webp":
            mime_type = "image/webp"

        # 1. Read image and convert to base64
        if source_image is not None:
            buf = io.BytesIO()
            fmt = "PNG" if ext == ".png" else "JPEG"
            if fmt == "JPEG" and source_image.mode in ("RGBA", "P"):
                source_image.convert("RGB").save(buf, format=fmt, quality=92)
            else:
                source_image.save(buf, format=fmt, quality=92 if fmt == "JPEG" else None)
            b64_data = base64.b64encode(buf.getvalue()).decode("utf-8")
        else:
            with open(image_path, "rb") as f:
                b64_data = base64.b64encode(f.read()).decode("utf-8")
            
        # 2. Build face tag overlays
        tags_html = ""
        for idx, t in enumerate(tags):
            # Map normalized center coordinates to top-left percentages
            left = max(0.0, min(100.0, (t['x'] - t['w'] / 2.0) * 100.0))
            top = max(0.0, min(100.0, (t['y'] - t['h'] / 2.0) * 100.0))
            w = max(0.0, min(100.0 - left, t['w'] * 100.0))
            h = max(0.0, min(100.0 - top, t['h'] * 100.0))
            
            raw_name = t['name'].strip() if t['name'] else str(idx + 1)
            name_escaped = html.escape(raw_name)
            
            tags_html += f"""
        <div class="face-tag" style="left: {left:.2f}%; top: {top:.2f}%; width: {w:.2f}%; height: {h:.2f}%;">
            <div class="tooltip" dir="auto">{name_escaped}</div>
        </div>"""

        # Description banner HTML
        desc_banner_html = ""
        if description:
            desc_escaped = html.escape(description)
            desc_banner_html = f'<div class="description-banner" dir="auto">Description: {desc_escaped}</div>'

        # 3. Construct self-contained HTML
        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Photo Tagger - Interactive View</title>
    <style>
        body {{
            margin: 0;
            padding: 0;
            background-color: #0f172a;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            font-family: '{font_family}', 'Segoe UI', Tahoma, Arial, sans-serif;
            color: #f1f5f9;
        }}
        .container {{
            position: relative;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
            border-radius: 12px;
            overflow: hidden;
            max-width: 95vw;
            max-height: 95vh;
            display: inline-block;
        }}
        img {{
            display: block;
            max-width: 100%;
            max-height: 95vh;
            object-fit: contain;
        }}
        .face-tag {{
            position: absolute;
            border: 2px solid transparent;
            border-radius: 6px;
            transition: all 0.2s ease-in-out;
            cursor: pointer;
            box-sizing: border-box;
        }}
        .face-tag:hover {{
            border-color: {hover_hex};
            box-shadow: 0 0 12px {shadow_rgba};
            background-color: {bg_hover};
        }}
        .tooltip {{
            position: absolute;
            bottom: calc(100% + 8px);
            left: 50%;
            transform: translateX(-50%) scale(0.95);
            background-color: {color_hex};
            color: white;
            padding: 6px 12px;
            border-radius: 6px;
            font-size: {font_size_px}px;
            font-weight: bold;
            white-space: nowrap;
            unicode-bidi: plaintext;
            opacity: 0;
            visibility: hidden;
            pointer-events: none;
            transition: all 0.15s cubic-bezier(0.4, 0, 0.2, 1);
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.3);
            z-index: 10;
        }}
        .tooltip::after {{
            content: '';
            position: absolute;
            top: 100%;
            left: 50%;
            transform: translateX(-50%);
            border-width: 6px;
            border-style: solid;
            border-color: {color_hex} transparent transparent transparent;
        }}
        .face-tag:hover .tooltip {{
            opacity: 1;
            visibility: visible;
            transform: translateX(-50%) scale(1);
        }}
        .description-banner {{
            position: absolute;
            bottom: 0;
            left: 0;
            right: 0;
            background-color: rgba(30, 41, 59, 0.9);
            backdrop-filter: blur(8px);
            padding: 12px;
            text-align: center;
            font-size: 14px;
            font-style: italic;
            border-top: 1px solid rgba(255, 255, 255, 0.1);
            transition: opacity 0.3s ease;
            opacity: 0;
            pointer-events: none;
        }}
        .container:hover .description-banner {{
            opacity: 1;
        }}
        .container:has(.face-tag:hover) .description-banner {{
            opacity: 0;
        }}
    </style>
</head>
<body>
    <div class="container">
        <img src="data:{mime_type};base64,{b64_data}" alt="Tagged Photo">
        {tags_html}
        {desc_banner_html}
    </div>
</body>
</html>
"""
        html_path = os.path.splitext(image_path)[0] + "_interactive.html"
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        return True
    except Exception as e:
        print(f"Error exporting interactive HTML: {e}")
        return False

def write_interactive_svg(image_path, tags, description, color_style=None, font_size_style=None, font_family="Segoe UI", source_image=None):
    """
    Exports a standalone interactive SVG file packaging the image (in Base64)
    with SVG rect overlays and native hover tooltips.
    """
    import base64
    import os
    import io
    try:
        # Get custom styling or defaults
        color_hex = color_style.get("hex", "#38bdf8") if color_style else "#38bdf8"
        bg_hover = color_style.get("hover", "rgba(56, 189, 248, 0.15)") if color_style else "rgba(56, 189, 248, 0.15)"

        # Determine mime-type from extension
        ext = os.path.splitext(image_path)[1].lower() if isinstance(image_path, str) else ".jpg"
        mime_type = "image/jpeg"
        if ext == ".png":
            mime_type = "image/png"
        elif ext == ".webp":
            mime_type = "image/webp"

        # 1. Get image dimensions & b64
        if source_image is not None:
            width, height = source_image.size
            buf = io.BytesIO()
            fmt = "PNG" if ext == ".png" else "JPEG"
            if fmt == "JPEG" and source_image.mode in ("RGBA", "P"):
                source_image.convert("RGB").save(buf, format=fmt, quality=92)
            else:
                source_image.save(buf, format=fmt, quality=92 if fmt == "JPEG" else None)
            b64_data = base64.b64encode(buf.getvalue()).decode("utf-8")
        else:
            with Image.open(image_path) as img:
                width, height = img.size
            with open(image_path, "rb") as f:
                b64_data = base64.b64encode(f.read()).decode("utf-8")
            
        # 3. Build face tag overlays in SVG rects
        rects_svg = ""
        for idx, t in enumerate(tags):
            # Map normalized center coordinates to absolute pixel coordinates
            left = (t['x'] - t['w'] / 2.0) * width
            top = (t['y'] - t['h'] / 2.0) * height
            w = t['w'] * width
            h = t['h'] * height
            
            raw_name = t['name'].strip() if t['name'] else str(idx + 1)
            name_escaped = html.escape(raw_name)
            
            rects_svg += f"""
  <rect class="face-box" x="{left:.1f}" y="{top:.1f}" width="{w:.1f}" height="{h:.1f}">
    <title>{name_escaped}</title>
  </rect>"""

        # Description banner in SVG
        desc_banner_svg = ""
        if description:
            banner_h = 40
            banner_y = height - banner_h
            desc_escaped = html.escape(description)
            desc_banner_svg = f"""
  <g class="desc-banner">
    <rect x="0" y="{banner_y}" width="{width}" height="{banner_h}" fill="#1e293b" fill-opacity="0.85" />
    <text x="{width // 2}" y="{banner_y + 24}" fill="#f1f5f9" font-family="{font_family}, Segoe UI, Tahoma, Arial, sans-serif" font-size="16" font-style="italic" text-anchor="middle" direction="auto" unicode-bidi="plaintext">Description: {desc_escaped}</text>
  </g>"""

        # 4. Construct SVG content
        svg_content = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" height="100%">
  <style>
    .face-box {{
      fill: rgba(0, 0, 0, 0);
      stroke: transparent;
      stroke-width: 3;
      transition: all 0.2s ease-in-out;
      cursor: pointer;
      pointer-events: all;
    }}
    .face-box:hover {{
      stroke: {color_hex};
      fill: {bg_hover};
    }}
    .desc-banner {{
      transition: opacity 0.3s ease;
      opacity: 0;
      pointer-events: none;
    }}
    svg:hover .desc-banner {{
      opacity: 1;
    }}
    /* Hide description banner when hovering a face */
    svg:has(.face-box:hover) .desc-banner {{
      opacity: 0;
    }}
  </style>
  <image href="data:{mime_type};base64,{b64_data}" x="0" y="0" width="{width}" height="{height}" />
  {rects_svg}
  {desc_banner_svg}
</svg>
"""
        svg_path = os.path.splitext(image_path)[0] + "_interactive.svg"
        with open(svg_path, "w", encoding="utf-8") as f:
            f.write(svg_content)
        return True
    except Exception as e:
        print(f"Error exporting interactive SVG: {e}")
        return False

class BadgeMetrics(tuple):
    """
    Subclasses tuple (width, height, is_pill) for backward compatibility
    with `badge_w, badge_h, is_pill = compute_badge_metrics(...)` while
    providing .corner_radius and .shape attributes.
    """
    def __new__(cls, width: int, height: int, is_pill: bool, corner_radius: int = 0, shape: str = "auto"):
        return super().__new__(cls, (int(width), int(height), bool(is_pill)))

    def __init__(self, width: int, height: int, is_pill: bool, corner_radius: int = 0, shape: str = "auto"):
        self.corner_radius = int(corner_radius)
        self.shape = str(shape)

    @property
    def width(self) -> int:
        return self[0]

    @property
    def height(self) -> int:
        return self[1]

    @property
    def is_pill(self) -> bool:
        return self[2]


def compute_badge_metrics(num_val, base_radius, badge_shape="auto"):
    """
    Computes BadgeMetrics(width, height, is_pill, corner_radius, shape) for badge numbering (1..999).
    Canonical shapes: 'auto', 'rounded_square', 'square'.
    - 'auto': Uses a circle for single digits (2r x 2r), cleanly expands into horizontal pill for 2+ digits (W x 2r).
    - 'rounded_square': Genuine square (W x W) with visible corner radius rc = max(3, int(base_radius * 0.35)).
    - 'square': Genuine sharp square (W x W) with corner radius 0.
    Both Square and Rounded Square maintain genuine 1:1 square geometry across 1, 10, 125, 999.
    """
    from models import normalize_badge_shape
    shape = normalize_badge_shape(badge_shape)
    s = str(num_val)
    n = len(s)
    
    # Calculate dimensions
    if shape in ("square", "rounded_square"):
        # Genuine square: width and height are strictly equal!
        if n <= 1:
            side = int(2 * base_radius)
        elif n == 2:
            side = int(2.4 * base_radius)
        elif n == 3:
            side = int(3.0 * base_radius)
        else:
            side = int((2.0 + 0.5 * (n - 1)) * base_radius)
        w = side
        h = side
    else:
        # Auto: circle for single digit, horizontal pill for multi-digits
        h = int(2 * base_radius)
        if n <= 1:
            w = int(2 * base_radius)
        elif n == 2:
            w = int(2.4 * base_radius)
        elif n == 3:
            w = int(3.0 * base_radius)
        else:
            w = int((2.0 + 0.5 * (n - 1)) * base_radius)
        
    if shape == "square":
        corner_radius = 0
        is_pill = (n > 1)
    elif shape == "rounded_square":
        corner_radius = max(3, int(base_radius * 0.35))
        is_pill = (n > 1)
    else: # "auto"
        corner_radius = base_radius
        is_pill = (n > 1)
        
    return BadgeMetrics(w, h, is_pill, corner_radius=corner_radius, shape=shape)


def get_badge_radius(image_width, image_height, font_size_style=None):
    """
    Returns image-space uniform badge radius across all tags.
    """
    scale_factor = font_size_style.get("scale", 1.0) if font_size_style else 1.0
    font_size = max(14, int(min(image_width, image_height) / 50 * scale_factor))
    return max(14, int(font_size * 0.95 * scale_factor))


# Arabic and Persian presentation forms and shaping
ARABIC_FORMS = {
    '\u0622': ('\uFE81', '\uFE82', '\uFE81', '\uFE82'), # آ
    '\u0623': ('\uFE83', '\uFE84', '\uFE83', '\uFE84'), # أ
    '\u0624': ('\uFE85', '\uFE86', '\uFE85', '\uFE86'), # ؤ
    '\u0625': ('\uFE87', '\uFE88', '\uFE87', '\uFE88'), # إ
    '\u0626': ('\uFE89', '\uFE8A', '\uFE8B', '\uFE8C'), # ئ
    '\u0627': ('\uFE8D', '\uFE8E', '\uFE8D', '\uFE8E'), # ا
    '\u0628': ('\uFE8F', '\uFE90', '\uFE91', '\uFE92'), # ب
    '\u067E': ('\uFB56', '\uFB57', '\uFB58', '\uFB59'), # پ
    '\u0629': ('\uFE93', '\uFE94', '\uFE93', '\uFE94'), # ة
    '\u062A': ('\uFE95', '\uFE96', '\uFE97', '\uFE98'), # ت
    '\u062B': ('\uFE99', '\uFE9A', '\uFE9B', '\uFE9C'), # ث
    '\u062C': ('\uFE9D', '\uFE9E', '\uFE9F', '\uFEA0'), # ج
    '\u0686': ('\uFB7A', '\uFB7B', '\uFB7C', '\uFB7D'), # چ
    '\u062D': ('\uFEA1', '\uFEA2', '\uFEA3', '\uFEA4'), # ح
    '\u062E': ('\uFEA5', '\uFEA6', '\uFEA7', '\uFEA8'), # خ
    '\u062F': ('\uFEA9', '\uFEAA', '\uFEA9', '\uFEAA'), # د
    '\u0630': ('\uFEAB', '\uFEAC', '\uFEAB', '\uFEAC'), # ذ
    '\u0631': ('\uFEAD', '\uFEAE', '\uFEAD', '\uFEAE'), # ر
    '\u0632': ('\uFEAF', '\uFEB0', '\uFEAF', '\uFEB0'), # ز
    '\u0698': ('\uFB8A', '\uFB8B', '\uFB8A', '\uFB8B'), # ژ
    '\u0633': ('\uFEB1', '\uFEB2', '\uFEB3', '\uFEB4'), # س
    '\u0634': ('\uFEB5', '\uFEB6', '\uFEB7', '\uFEB8'), # ش
    '\u0635': ('\uFEB9', '\uFEBA', '\uFEBB', '\uFEBC'), # ص
    '\u0636': ('\uFEBD', '\uFEBE', '\uFEBF', '\uFEC0'), # ض
    '\u0637': ('\uFEC1', '\uFEC2', '\uFEC3', '\uFEC4'), # ط
    '\u0638': ('\uFEC5', '\uFEC6', '\uFEC7', '\uFEC8'), # ظ
    '\u0639': ('\uFEC9', '\uFECA', '\uFECB', '\uFECC'), # ع
    '\u063A': ('\uFECD', '\uFECE', '\uFECF', '\uFED0'), # غ
    '\u0641': ('\uFED1', '\uFED2', '\uFED3', '\uFED4'), # ف
    '\u0642': ('\uFED5', '\uFED6', '\uFED7', '\uFED8'), # ق
    '\u06A9': ('\uFB8E', '\uFB8F', '\uFB90', '\uFB91'), # ک
    '\u0643': ('\uFED9', '\uFEDA', '\uFEDB', '\uFEDC'), # ك
    '\u06AF': ('\uFB92', '\uFB93', '\uFB94', '\uFB95'), # گ
    '\u0644': ('\uFEDD', '\uFEDE', '\uFEDF', '\uFEE0'), # ل
    '\u0645': ('\uFEE1', '\uFEE2', '\uFEE3', '\uFEE4'), # م
    '\u0646': ('\uFEE5', '\uFEE6', '\uFEE7', '\uFEE8'), # ن
    '\u0648': ('\uFEE9', '\uFEEA', '\uFEE9', '\uFEEA'), # و
    '\u0647': ('\uFEEB', '\uFEEC', '\uFEED', '\uFEEE'), # ه
    '\u0649': ('\uFEEF', '\uFEF0', '\uFEEF', '\uFEF0'), # ى
    '\u06CC': ('\uFBFC', '\uFBFD', '\uFBFE', '\uFBFF'), # ی
    '\u064A': ('\uFEF1', '\uFEF2', '\uFEF3', '\uFEF4'), # ي
}

ARABIC_RIGHT_JOINING = {
    '\u0622', '\u0623', '\u0624', '\u0625', '\u0627',
    '\u062F', '\u0630', '\u0631', '\u0632', '\u0698', '\u0648'
}


try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    _HAS_PROVEN_SHAPER = True
    _SHAPER_BACKEND = "arabic-reshaper+python-bidi"
    _reshaper_config = {
        'delete_harakat': False,
        'support_ligatures': True,
        'persian': True,
    }
    _custom_reshaper = arabic_reshaper.ArabicReshaper(configuration=_reshaper_config)
except ImportError as _e:
    _HAS_PROVEN_SHAPER = False
    _custom_reshaper = None
    _SHAPER_BACKEND = "pure-python-fallback"
    import sys
    sys.stderr.write(f"[PhotoTagger Notice] Package '{_e.name}' not available; pure-Python Persian/Arabic shaping fallback is active.\n")


def is_arabic_char(c):
    cp = ord(c)
    return (
        (0x0600 <= cp <= 0x06FF) or
        (0x0750 <= cp <= 0x077F) or
        (0x08A0 <= cp <= 0x08FF) or
        (0xFB50 <= cp <= 0xFDFF) or
        (0xFE70 <= cp <= 0xFEFF) or
        cp == 0x200C or cp == 0x200D
    )


def _shape_arabic_word(w):
    n = len(w)
    out = []
    i = 0
    while i < n:
        c = w[i]
        if c not in ARABIC_FORMS:
            out.append(c)
            i += 1
            continue
        # Lam-Alef ligatures
        if c == '\u0644' and i + 1 < n and w[i+1] in ('\u0622', '\u0623', '\u0625', '\u0627'):
            alef = w[i+1]
            prev_j = (i > 0 and w[i-1] in ARABIC_FORMS and w[i-1] not in ARABIC_RIGHT_JOINING)
            if alef == '\u0622':
                out.append('\uFEF6' if prev_j else '\uFEF5')
            elif alef == '\u0623':
                out.append('\uFEF8' if prev_j else '\uFEF7')
            elif alef == '\u0625':
                out.append('\uFEFA' if prev_j else '\uFEF9')
            else:
                out.append('\uFEFC' if prev_j else '\uFEFB')
            i += 2
            continue
        prev_j = (i > 0 and w[i-1] in ARABIC_FORMS and w[i-1] not in ARABIC_RIGHT_JOINING)
        next_j = (i + 1 < n and w[i+1] in ARABIC_FORMS)
        shapes = ARABIC_FORMS[c]
        if prev_j and next_j and c not in ARABIC_RIGHT_JOINING:
            out.append(shapes[3])
        elif prev_j:
            out.append(shapes[1])
        elif next_j and c not in ARABIC_RIGHT_JOINING:
            out.append(shapes[2])
        else:
            out.append(shapes[0])
        i += 1
    return ''.join(out)


def shape_persian_arabic_text(text):
    """
    Shapes Arabic/Persian cursive letters into contextual presentation forms
    and applies standard Unicode Bidirectional Algorithm (UBA / UAX #9)
    for correct RTL display in LTR raster renderers.
    Handles Persian letters (گ, چ, پ, ژ, ک, ی), ZWNJ, diacritics, and mixed English/Persian.
    """
    if not text or not any(is_arabic_char(c) for c in text):
        return text

    if _HAS_PROVEN_SHAPER and _custom_reshaper is not None:
        try:
            reshaped = _custom_reshaper.reshape(text)
            return get_display(reshaped)
        except Exception:
            pass

    # Pure-Python fallback when external packages are not installed
    tokens = []
    curr = []
    curr_is_ar = False
    for c in text:
        is_ar = is_arabic_char(c)
        if not curr:
            curr.append(c)
            curr_is_ar = is_ar
        elif is_ar == curr_is_ar:
            curr.append(c)
        else:
            tokens.append((''.join(curr), curr_is_ar))
            curr = [c]
            curr_is_ar = is_ar
    if curr:
        tokens.append((''.join(curr), curr_is_ar))
    
    shaped_tokens = []
    for tok, is_ar in tokens:
        if is_ar:
            shaped_tokens.append(''.join(reversed(_shape_arabic_word(tok))))
        else:
            shaped_tokens.append(tok)
    return ''.join(reversed(shaped_tokens))


def get_luminance(rgb):
    """Computes relative luminance of an RGB tuple (0.0 to 1.0)."""
    r, g, b = rgb[:3]
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0

def get_contrasting_colors(fill_rgb):
    """
    Mathematically computes WCAG contrasting text and keyline colors based on fill luminance.
    Returns (text_rgba, keyline_rgba).
    """
    lum = get_luminance(fill_rgb)
    if lum > 0.5:
        # Light fill -> dark slate text and black keyline
        return (15, 23, 42, 255), (0, 0, 0, 255)
    else:
        # Dark fill -> pure white text and crisp white keyline
        return (255, 255, 255, 255), (255, 255, 255, 255)


PRESETS = ["Classic", "High Contrast", "Minimal", "Borderless", "Single Outline", "Print"]


def get_preset_rendering_properties(style_preset="Classic", color_style=None):
    """
    Returns unified styling properties:
    (badge_rgb, badge_text_rgb, badge_keyline_rgb, legend_bg, legend_text, legend_header, legend_divider)
    Guarantees readable text/stroke for the actual fill and retains the preset's legend treatment.
    A preset populates defaults, and a subsequent swatch click overrides the badge accent for EVERY preset.
    """
    p = str(style_preset or "Classic").strip().lower()
    if "outline" in p: # Single Outline preset
        preset_name = "Single Outline"
        stroke_width = 1
        shape = "auto"
        default_badge_rgb = (255, 255, 255)         # Crisp white default
        default_text_rgb = (15, 23, 42, 255)
        legend_bg = (36, 40, 48, 255)               # Charcoal #242830
        legend_text = (241, 245, 249, 255)
        legend_header = (129, 140, 248, 255)        # Indigo #818cf8
        legend_divider = (56, 64, 78, 255)          # Border #38404E
    elif "borderless" in p: # Borderless preset: solid badges, zero stroke, regular scale
        preset_name = "Borderless"
        stroke_width = 0
        shape = "auto"
        default_badge_rgb = (13, 148, 136)          # Teal #0d9488
        default_text_rgb = (255, 255, 255, 255)
        legend_bg = (36, 40, 48, 255)               # Charcoal #242830
        legend_text = (226, 232, 240, 255)
        legend_header = (129, 140, 248, 255)
        legend_divider = (56, 64, 78, 255)
    elif "high" in p:
        preset_name = "High Contrast"
        stroke_width = 1
        shape = "auto"
        default_badge_rgb = (234, 179, 8)           # Yellow #eab308
        default_text_rgb = (0, 0, 0, 255)           # Black text for AAA contrast
        legend_bg = (10, 10, 15, 255)               # Ultra dark slate
        legend_text = (255, 255, 255, 255)          # Pure white
        legend_header = (250, 204, 21, 255)         # Bright yellow
        legend_divider = (250, 204, 21, 255)
    elif "print" in p:
        preset_name = "Print"
        stroke_width = 1
        shape = "square"
        default_badge_rgb = (255, 255, 255)         # White paper badge by default
        default_text_rgb = (0, 0, 0, 255)           # Crisp black text
        legend_bg = (255, 255, 255, 255)            # Clean white paper background
        legend_text = (15, 23, 42, 255)             # Dark slate text
        legend_header = (30, 58, 138, 255)          # Navy header
        legend_divider = (203, 213, 225, 255)       # Light gray line
    elif "minimal" in p:
        preset_name = "Minimal"
        stroke_width = 0
        shape = "auto"
        default_badge_rgb = (241, 245, 249)         # Quiet light fill #f1f5f9
        default_text_rgb = (15, 23, 42, 255)        # Dark slate text
        legend_bg = (36, 40, 48, 255)               # Charcoal #242830
        legend_text = (226, 232, 240, 255)
        legend_header = (148, 163, 184, 255)
        legend_divider = (56, 64, 78, 255)
    else: # Classic
        preset_name = "Classic"
        stroke_width = 1
        shape = "auto"
        default_badge_rgb = (13, 148, 136)          # Teal #0d9488
        default_text_rgb = (255, 255, 255, 255)
        legend_bg = (36, 40, 48, 255)               # Charcoal #242830
        legend_text = (226, 232, 240, 255)
        legend_header = None
        legend_divider = None

    if color_style and isinstance(color_style, dict) and "rgb" in color_style:
        badge_rgb = color_style["rgb"]
        calc_text, calc_keyline = get_contrasting_colors(badge_rgb)
        badge_text_rgb = calc_text
        badge_keyline_rgb = calc_keyline
    else:
        badge_rgb = default_badge_rgb
        calc_text, calc_keyline = get_contrasting_colors(badge_rgb)
        badge_text_rgb = default_text_rgb if default_text_rgb else calc_text
        badge_keyline_rgb = calc_keyline

    if legend_header is None:
        legend_header = badge_rgb + (255,) if len(badge_rgb) == 3 else badge_rgb
    if legend_divider is None:
        legend_divider = badge_rgb + (255,) if len(badge_rgb) == 3 else badge_rgb

    return {
        "name": preset_name,
        "stroke_width": stroke_width,
        "shape": shape,
        "shadow_width": 0,
        "shadow_rgb": None,
        "halo_rgb": None,
        "keyline_rgb": badge_keyline_rgb[:3] if len(badge_keyline_rgb) >= 3 else badge_keyline_rgb,
        "badge_rgb": badge_rgb,
        "badge_text_rgb": badge_text_rgb,
        "badge_keyline_rgb": badge_keyline_rgb,
        "legend_bg": legend_bg,
        "legend_text": legend_text,
        "legend_header": legend_header,
        "legend_divider": legend_divider,
    }


def compute_default_badge_positions(tags, width, height, font_size_style=None, badge_shape="auto"):
    """
    Computes unified normalized (bx, by) badge positions for all tags:
    - If a tag already has manual overrides ('bx', 'by'), preserves them.
    - Otherwise, computes collision-free automatic positions strictly outside face boxes,
      avoiding cross-person body masking and overlapping previous badges.
    Returns a list of (bx_norm, by_norm) corresponding 1:1 to the input tags list.
    """
    import math
    badge_r = get_badge_radius(width, height, font_size_style)
    
    all_face_boxes = []
    for t in tags:
        fl = int((t['x'] - t['w'] / 2.0) * width)
        ft = int((t['y'] - t['h'] / 2.0) * height)
        fr = int((t['x'] + t['w'] / 2.0) * width)
        fb = int((t['y'] + t['h'] / 2.0) * height)
        fl = max(0, min(width - 1, fl))
        ft = max(0, min(height - 1, ft))
        fr = max(0, min(width - 1, fr))
        fb = max(0, min(height - 1, fb))
        fw = max(1, fr - fl)
        fh = max(1, fb - ft)
        cx = int(fl + fw / 2.0)
        cy = int(ft + fh / 2.0)
        all_face_boxes.append({
            'fl': fl, 'ft': ft, 'fr': fr, 'fb': fb,
            'cx': cx, 'cy': cy, 'fw': fw, 'fh': fh
        })

    def badge_rect_intersects_rect(bx, by, bw, bh, x1, y1, x2, y2, margin=1):
        bl = bx - bw - margin
        br = bx + bw + margin
        bt = by - bh - margin
        bb = by + bh + margin
        return not (br < x1 or bl > x2 or bb < y1 or bt > y2)

    placed_badges = []
    def is_valid_badge_placement(bx, by, bw, bh, person_idx):
        if bx - bw < 2 or bx + bw > width - 2 or by - bh < 2 or by + bh > height - 2:
            return False
        for data in all_face_boxes:
            if badge_rect_intersects_rect(bx, by, bw, bh, data['fl'], data['ft'], data['fr'], data['fb'], margin=1):
                return False
        for k, data in enumerate(all_face_boxes):
            if k != person_idx:
                k_body_l = data['fl'] - int(data['fw'] * 0.1)
                k_body_r = data['fr'] + int(data['fw'] * 0.1)
                k_body_t = data['fb'] + 1
                k_body_b = min(height, data['fb'] + int(data['fh'] * 1.2))
                if badge_rect_intersects_rect(bx, by, bw, bh, k_body_l, k_body_t, k_body_r, k_body_b, margin=1):
                    return False
        min_gap = 2
        for prev_x, prev_y, prev_bw, prev_bh in placed_badges:
            dx = abs(bx - prev_x)
            dy = abs(by - prev_y)
            if dx < (bw + prev_bw + min_gap) and dy < (bh + prev_bh + min_gap):
                return False
        return True

    positions = []
    for idx, t in enumerate(tags):
        num_str = str(idx + 1)
        metrics = compute_badge_metrics(num_str, badge_r, badge_shape=badge_shape)
        bw = metrics.width // 2
        bh = metrics.height // 2
        
        chosen_pos = None
        if t.get('bx') is not None and t.get('by') is not None:
            bx_custom = int(t['bx'] * width)
            by_custom = int(t['by'] * height)
            chosen_pos = (bx_custom, by_custom)
        else:
            box_i = all_face_boxes[idx]
            fl_i, ft_i, fr_i, fb_i = box_i['fl'], box_i['ft'], box_i['fr'], box_i['fb']
            fw_i, _, cx_i, cy_i = box_i['fw'], box_i['fh'], box_i['cx'], box_i['cy']
            
            candidates = [
                (cx_i, fb_i + badge_r + 2),
                (cx_i, ft_i - badge_r - 2),
                (cx_i - int(fw_i * 0.35), ft_i - badge_r - 2),
                (cx_i + int(fw_i * 0.35), ft_i - badge_r - 2),
                (cx_i - int(fw_i * 0.35), fb_i + badge_r + 2),
                (cx_i + int(fw_i * 0.35), fb_i + badge_r + 2),
                (fl_i - badge_r - 2, cy_i),
                (fr_i + badge_r + 2, cy_i),
            ]
            for cand_x, cand_y in candidates:
                if is_valid_badge_placement(cand_x, cand_y, bw, bh, idx):
                    chosen_pos = (cand_x, cand_y)
                    break
            if chosen_pos is None:
                base_x, base_y = cx_i, ft_i - badge_r - 2
                found_spiral = False
                for dist in range(3, 150, 3):
                    for angle_deg in range(0, 360, 30):
                        rad = math.radians(angle_deg)
                        sx = int(base_x + dist * math.cos(rad))
                        sy = int(base_y + dist * math.sin(rad))
                        if is_valid_badge_placement(sx, sy, bw, bh, idx):
                            chosen_pos = (sx, sy)
                            found_spiral = True
                            break
                    if found_spiral:
                        break
            if chosen_pos is None:
                bx = max(badge_r + 2, min(width - badge_r - 2, cx_i))
                by = max(badge_r + 2, min(height - badge_r - 2, ft_i - badge_r - 2))
                chosen_pos = (bx, by)
                
        bx, by = chosen_pos
        placed_badges.append((bx, by, bw, bh))
        positions.append((bx / float(width), by / float(height)))
        
    return positions


def draw_annotations_on_image(
    image_path,
    tags,
    output_path=None,
    draw_names=False,
    color_style=None,
    font_size_style=None,
    description=None,
    for_editor=False,
    style_preset="Classic",
    badge_shape="auto",
    font_family="Segoe UI"
):
    """
    Reads the image, draws bounding boxes and labels for each tag, and renders the result.
    - If output_path is None: returns the final rendered PIL Image directly in-memory.
    - If output_path is provided: saves to disk and returns True.
    - Supports truthful appearance presets (Classic, High Contrast, Minimal, Print).
    - Preserves Unicode accents, non-Latin, and Persian/Arabic shaped text.
    - Supports badge shapes: 'auto' (circle/pill), 'rounded_square', 'square'.
    - Supports tag font families: 'Segoe UI' (default), 'Tahoma', 'Arial'.
    """
    try:
        import math
        from PIL import Image, ImageDraw, ImageFont
        tags = sort_faces_spatial(tags)
        
        if isinstance(image_path, Image.Image):
            annotated = image_path.copy()
        else:
            with Image.open(image_path) as img:
                annotated = img.copy()
                
        width, height = annotated.size
        
        if annotated.mode not in ('RGB', 'RGBA'):
            annotated = annotated.convert('RGB')
            
        draw = ImageDraw.Draw(annotated, 'RGBA')
        
        props = get_preset_rendering_properties(style_preset=style_preset, color_style=color_style)
        box_color = props["badge_rgb"]
        box_color_rgba = box_color + (255,)
        badge_text_rgba = props["badge_text_rgb"]
        
        line_width = max(2, int(min(width, height) / 300))
        scale_factor = font_size_style.get("scale", 1.0) if font_size_style else 1.0
        font_size = max(14, int(min(width, height) / 50 * scale_factor))
        
        font_paths = resolve_font_files_for_family(font_family)
        font = None
        for path in font_paths:
            try:
                font = ImageFont.truetype(path, font_size)
                break
            except IOError:
                continue
        if font is None:
            font = ImageFont.load_default()
            
        if not draw_names:
            # ----------------------------------------------------
            # Output 2-a: Numbered
            # ----------------------------------------------------
            for idx, t in enumerate(tags):
                left = int((t['x'] - t['w'] / 2.0) * width)
                top = int((t['y'] - t['h'] / 2.0) * height)
                right = int((t['x'] + t['w'] / 2.0) * width)
                bottom = int((t['y'] + t['h'] / 2.0) * height)
                
                left = max(0, min(width - 1, left))
                top = max(0, min(height - 1, top))
                right = max(0, min(width - 1, right))
                bottom = max(0, min(height - 1, bottom))
                
                draw.rectangle([left, top, right, bottom], outline=box_color_rgba, width=line_width)
                text = str(idx + 1)
                
                try:
                    tb = draw.textbbox((0, 0), text, font=font)
                    text_w = tb[2] - tb[0]
                    text_h = tb[3] - tb[1]
                except AttributeError:
                    text_w, text_h = draw.textsize(text, font=font)
                    
                padding = max(3, font_size // 5)
                text_y = top - text_h - padding * 2
                if text_y < 0:
                    text_y = top + padding
                    
                bg_rect = [left, text_y, left + text_w + padding * 2, text_y + text_h + padding * 2]
                draw.rectangle(bg_rect, fill=(17, 24, 39, 220), outline=box_color_rgba, width=1)
                draw.text((left + padding, text_y + padding), text, font=font, fill=badge_text_rgba)
                
            final_output_img = annotated
        else:
            # ----------------------------------------------------
            # Output 2-b: Tagged
            # ----------------------------------------------------
            from models import normalize_badge_shape
            norm_shape = normalize_badge_shape(badge_shape)
            positions = compute_default_badge_positions(tags, width, height, font_size_style, badge_shape=norm_shape)
            badge_r = get_badge_radius(width, height, font_size_style)
            
            for idx, t in enumerate(tags):
                bx_norm, by_norm = positions[idx]
                t['bx'] = bx_norm
                t['by'] = by_norm
                
                bx = int(bx_norm * width)
                by = int(by_norm * height)
                num_str = str(idx + 1)
                metrics = compute_badge_metrics(num_str, badge_r, badge_shape=norm_shape)
                bw = metrics.width // 2
                bh = metrics.height // 2
                
                if not for_editor:
                    preset_lower = str(style_preset or "Classic").strip().lower()
                    is_single_outline = "outline" in preset_lower
                    is_minimal = "minimal" in preset_lower
                    is_borderless = "borderless" in preset_lower
                    is_print = "print" in preset_lower

                    num_fill = badge_text_rgba
                    keyline_rgba = props.get("badge_keyline_rgb", (255, 255, 255, 255))

                    if is_single_outline:
                        # Exactly one visible perimeter on circles and rectangles, without a halo, inset line or shadow
                        b_fill = box_color_rgba
                        b_outline = keyline_rgba
                        b_width = max(2, int(line_width * 0.75))
                    elif is_minimal or is_borderless:
                        # Minimal & Borderless: solid fill with no stroke
                        b_fill = box_color_rgba
                        b_outline = None
                        b_width = 0
                    elif is_print:
                        # Print uses an opaque rectangular badge with black/contrasting keyline and text
                        b_fill = box_color_rgba
                        b_outline = (0, 0, 0, 255) if box_color in ((255, 255, 255), (248, 250, 252)) else keyline_rgba
                        b_width = max(1, line_width // 2)
                    else:
                        # Classic & High Contrast: colored fill with contrasting keyline
                        b_fill = box_color_rgba
                        b_outline = keyline_rgba
                        b_width = max(1, line_width // 2)

                    shape_to_render = metrics.shape

                    if shape_to_render == "square":
                        draw.rectangle(
                            [bx - bw, by - bh, bx + bw, by + bh],
                            fill=b_fill,
                            outline=b_outline if b_width > 0 else None,
                            width=b_width
                        )
                    elif shape_to_render == "rounded_square":
                        draw.rounded_rectangle(
                            [bx - bw, by - bh, bx + bw, by + bh],
                            radius=metrics.corner_radius,
                            fill=b_fill,
                            outline=b_outline if b_width > 0 else None,
                            width=b_width
                        )
                    else: # auto
                        if not metrics.is_pill:
                            draw.ellipse(
                                [bx - badge_r, by - badge_r, bx + badge_r, by + badge_r],
                                fill=b_fill,
                                outline=b_outline if b_width > 0 else None,
                                width=b_width
                            )
                        else:
                            draw.rounded_rectangle(
                                [bx - bw, by - badge_r, bx + bw, by + badge_r],
                                radius=badge_r,
                                fill=b_fill,
                                outline=b_outline if b_width > 0 else None,
                                width=b_width
                            )

                    digit_count = len(num_str)
                    if digit_count <= 1:
                        badge_font_scale = 0.72
                    elif digit_count == 2:
                        badge_font_scale = 0.70
                    elif digit_count == 3:
                        badge_font_scale = 0.65
                    else:
                        badge_font_scale = 0.58
                        
                    badge_font_size = max(8, int(badge_r * badge_font_scale))
                    badge_font = None
                    for path in font_paths:
                        try:
                            badge_font = ImageFont.truetype(path, badge_font_size)
                            break
                        except IOError:
                            continue
                    if badge_font is None:
                        badge_font = font

                    try:
                        tb = draw.textbbox((0, 0), num_str, font=badge_font)
                        tw = tb[2] - tb[0]
                        th = tb[3] - tb[1]
                        tx_off, ty_off = tb[0], tb[1]
                    except AttributeError:
                        tw, th = draw.textsize(num_str, font=badge_font)
                        tx_off, ty_off = 0, 0

                    tx = bx - (tw / 2.0) - tx_off
                    ty = by - (th / 2.0) - ty_off
                    draw.text((tx, ty), num_str, font=badge_font, fill=num_fill if 'num_fill' in locals() else badge_text_rgba)
                
            # Free space footer under photo
            if description is None and not isinstance(image_path, Image.Image):
                try:
                    from PIL.ExifTags import TAGS
                    with Image.open(image_path) as img:
                        exif_data = img._getexif()
                        if exif_data:
                            for tag, value in exif_data.items():
                                decoded = TAGS.get(tag, tag)
                                if decoded == "ImageDescription":
                                    description = value
                                    break
                except Exception:
                    description = ''
                    
            desc_text = str(description).strip() if description else ""

            legend_font_size = max(13, int(min(width, height) / 48 * scale_factor))
            legend_font = None
            for path in font_paths:
                try:
                    legend_font = ImageFont.truetype(path, legend_font_size)
                    break
                except IOError:
                    continue
            if legend_font is None:
                legend_font = ImageFont.load_default()
                
            line_h = max(28, int(legend_font_size * 2.0))
            header_h = max(30, int(legend_font_size * 2.2))
            pad_top = max(16, int(legend_font_size * 1.0))
            pad_bottom = max(16, int(legend_font_size * 1.2))
            pad_left = max(20, int(width * 0.03))
            max_text_w = width - (pad_left * 2)
            
            # Wrap General Photo Description
            desc_lines = []
            if desc_text:
                for paragraph in desc_text.split('\n'):
                    words = paragraph.split(' ')
                    curr = []
                    for w in words:
                        test_str = ' '.join(curr + [w])
                        try:
                            tb = draw.textbbox((0, 0), test_str, font=legend_font)
                            tw = tb[2] - tb[0]
                        except AttributeError:
                            tw, _ = draw.textsize(test_str, font=legend_font)
                        if tw <= max_text_w or not curr:
                            curr.append(w)
                        else:
                            desc_lines.append(' '.join(curr))
                            curr = [w]
                    if curr:
                        desc_lines.append(' '.join(curr))
                        
            desc_block_h = (header_h + (len(desc_lines) * line_h) + int(line_h * 0.5)) if desc_lines else 0

            # Tagged Persons Grid Layout Pre-calculation
            num_tags = len(tags)
            tag_layouts = []
            row_heights = []
            num_cols = 1
            col_w = max_text_w
            line_spacing = legend_font_size + 4

            if num_tags > 0:
                avail_w = width - (pad_left * 2)
                num_cols = max(1, min(4, avail_w // 250))
                col_w = avail_w // num_cols
                
                for idx, t in enumerate(tags):
                    num_str = str(idx + 1)
                    raw_name = t.get('name', '').strip()
                    name_str = raw_name if raw_name else "(Unnamed)"
                    
                    try:
                        tb_n = draw.textbbox((0, 0), num_str, font=legend_font)
                        tw_n = tb_n[2] - tb_n[0]
                        th_n = tb_n[3] - tb_n[1]
                        tx_off, ty_off = tb_n[0], tb_n[1]
                    except AttributeError:
                        tw_n, th_n = draw.textsize(num_str, font=legend_font)
                        tx_off, ty_off = 0, 0
                        
                    pill_h = max(22, int(legend_font_size * 1.35))
                    if norm_shape in ("square", "rounded_square"):
                        pill_w = max(pill_h, tw_n + 10)
                        pill_h = pill_w  # Keep genuine square in legend badge
                    else:
                        pill_w = max(pill_h, tw_n + 12)
                    avail_name_w = col_w - pill_w - 18
                    
                    words = name_str.split(' ')
                    name_lines = []
                    curr_line = []
                    for w in words:
                        test = ' '.join(curr_line + [w]) if curr_line else w
                        try:
                            tb_test = draw.textbbox((0, 0), test, font=legend_font)
                            tw_test = tb_test[2] - tb_test[0]
                        except AttributeError:
                            tw_test, _ = draw.textsize(test, font=legend_font)
                        if tw_test <= avail_name_w or not curr_line:
                            curr_line.append(w)
                        else:
                            name_lines.append(' '.join(curr_line))
                            curr_line = [w]
                    if curr_line:
                        name_lines.append(' '.join(curr_line))
                        
                    tag_layouts.append({
                        'num_str': num_str,
                        'raw_name': raw_name,
                        'name_lines': name_lines,
                        'pill_w': pill_w,
                        'pill_h': pill_h,
                        'tw_n': tw_n,
                        'th_n': th_n,
                        'tx_off': tx_off,
                        'ty_off': ty_off
                    })
                    
                num_rows = math.ceil(num_tags / num_cols)
                for r in range(num_rows):
                    row_items = tag_layouts[r * num_cols : (r + 1) * num_cols]
                    max_lines = max(len(item['name_lines']) for item in row_items) if row_items else 1
                    r_h = max(line_h, max_lines * line_spacing + 8)
                    row_heights.append(r_h)

            tags_block_h = (header_h + sum(row_heights)) if num_tags > 0 else 0
            
            total_content_h = desc_block_h + tags_block_h
            footer_h = (pad_top + total_content_h + pad_bottom) if total_content_h > 0 else 0
                
            if footer_h > 0:
                total_height = height + footer_h
                final_output_img = Image.new('RGBA', (width, total_height), props["legend_bg"])
                final_output_img.paste(annotated, (0, 0))
                
                fdraw = ImageDraw.Draw(final_output_img)
                fdraw.line([(0, height), (width, height)], fill=props["legend_divider"], width=max(2, line_width))
                
                current_y = height + pad_top
                
                # Render Description Block
                if desc_lines:
                    fdraw.text((pad_left, current_y), "PHOTO DESCRIPTION", font=legend_font, fill=props["legend_header"])
                    current_y += header_h
                    for line in desc_lines:
                        shaped_line = shape_persian_arabic_text(line)
                        fdraw.text((pad_left, current_y), shaped_line, font=legend_font, fill=props["legend_text"])
                        current_y += line_h
                    current_y += int(line_h * 0.5)

                # Render Tagged Persons Block
                if num_tags > 0:
                    fdraw.text((pad_left, current_y), "TAGGED PERSONS", font=legend_font, fill=props["legend_header"])
                    current_y += header_h
                    
                    y_grid_start = current_y
                    for idx, layout in enumerate(tag_layouts):
                        row = idx // num_cols
                        col = idx % num_cols
                        
                        x_start = pad_left + col * col_w
                        y_row = y_grid_start + sum(row_heights[:row])
                        r_h = row_heights[row]
                        
                        pill_w = layout['pill_w']
                        pill_h = layout['pill_h']
                        
                        x_pill = x_start
                        y_pill = y_row + (r_h - pill_h) // 2
                        
                        preset_lower = str(style_preset or "Classic").strip().lower()
                        is_single_outline = "outline" in preset_lower
                        is_minimal = "minimal" in preset_lower
                        is_borderless = "borderless" in preset_lower
                        is_print = "print" in preset_lower

                        keyline_rgba = props.get("badge_keyline_rgb", (255, 255, 255, 255))
                        l_text_color = badge_text_rgba

                        if is_single_outline:
                            l_fill = box_color_rgba
                            l_outline = keyline_rgba
                            l_width = 1
                        elif is_minimal or is_borderless:
                            l_fill = box_color_rgba
                            l_outline = None
                            l_width = 0
                        elif is_print:
                            l_fill = box_color_rgba
                            l_outline = (0, 0, 0, 255) if box_color in ((255, 255, 255), (248, 250, 252)) else keyline_rgba
                            l_width = 1
                        else:
                            l_fill = box_color_rgba
                            l_outline = keyline_rgba
                            l_width = 1

                        shape_leg = norm_shape
                        if shape_leg == "square":
                            fdraw.rectangle([x_pill, y_pill, x_pill + pill_w, y_pill + pill_h], 
                                            fill=l_fill, 
                                            outline=l_outline if l_width > 0 else None, 
                                            width=l_width)
                        elif shape_leg == "rounded_square":
                            cr_legend = max(2, int(pill_h * 0.28))
                            fdraw.rounded_rectangle([x_pill, y_pill, x_pill + pill_w, y_pill + pill_h], 
                                                    radius=cr_legend, 
                                                    fill=l_fill, 
                                                    outline=l_outline if l_width > 0 else None, 
                                                    width=l_width)
                        else:
                            fdraw.rounded_rectangle([x_pill, y_pill, x_pill + pill_w, y_pill + pill_h], 
                                                    radius=pill_h // 2, 
                                                    fill=l_fill, 
                                                    outline=l_outline if l_width > 0 else None, 
                                                    width=l_width)
                            
                        ptx = x_pill + (pill_w - layout['tw_n']) / 2.0 - layout['tx_off']
                        pty = y_pill + (pill_h - layout['th_n']) / 2.0 - layout['ty_off']
                        fdraw.text((ptx, pty), layout['num_str'], font=legend_font, fill=l_text_color)
                        
                        name_x = x_pill + pill_w + 10
                        if layout['raw_name']:
                            name_color = props["legend_text"]
                        else:
                            name_color = (148, 163, 184, 255) if "print" not in str(style_preset).lower() else (100, 116, 139, 255)
                            
                        total_name_h = len(layout['name_lines']) * line_spacing
                        name_y_start = y_row + (r_h - total_name_h) // 2
                        
                        for l_idx, line_txt in enumerate(layout['name_lines']):
                            line_y = name_y_start + l_idx * line_spacing
                            shaped_name = shape_persian_arabic_text(line_txt)
                            fdraw.text((name_x, line_y), shaped_name, font=legend_font, fill=name_color)
            else:
                final_output_img = annotated
                
        if output_path is None:
            return final_output_img
            
        ext = os.path.splitext(output_path)[1].lower()
        if ext in ('.jpg', '.jpeg'):
            fmt = 'JPEG'
        elif ext == '.png':
            fmt = 'PNG'
        elif ext == '.webp':
            fmt = 'WEBP'
        else:
            fmt = 'JPEG'
            
        if fmt == 'JPEG' and final_output_img.mode in ('RGBA', 'LA'):
            final_output_img = final_output_img.convert('RGB')
            
        save_params = {'format': fmt}
        if fmt == 'JPEG':
            save_params['quality'] = 95
        elif fmt == 'WEBP':
            save_params['quality'] = 95
            
        final_output_img.save(output_path, **save_params)
        return True
    except Exception as e:
        print(f"Error drawing annotations on image: {e}")
        return False
