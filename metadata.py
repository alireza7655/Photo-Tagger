try:
    import defusedxml.ElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET
import html
import re
import os
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
            
        # Replace target path with the newly tagged file
        if os.path.exists(temp_path):
            if os.path.exists(image_path) and os.path.abspath(image_path) != os.path.abspath(load_path):
                # If we are converting formats to a different file name, don't remove the original source file!
                if os.path.exists(image_path):
                    os.remove(image_path)
            elif os.path.exists(image_path):
                os.remove(image_path)
            os.rename(temp_path, image_path)
            return True
    except Exception as e:
        print(f"Error saving metadata for {image_path}: {e}")
        # Clean up temp file if exists
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except:
            pass
        return False

def write_interactive_html(image_path, tags, description, color_style=None, font_size_style=None):
    """
    Exports a standalone interactive HTML file packaging the image (in Base64)
    with CSS-styled hover overlays and tooltips.
    """
    import base64
    import os
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
        ext = os.path.splitext(image_path)[1].lower()
        mime_type = "image/jpeg"
        if ext == ".png":
            mime_type = "image/png"
        elif ext == ".webp":
            mime_type = "image/webp"

        # 1. Read image and convert to base64
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
            <div class="tooltip">{name_escaped}</div>
        </div>"""

        # Description banner HTML
        desc_banner_html = ""
        if description:
            desc_escaped = html.escape(description)
            desc_banner_html = f'<div class="description-banner">Description: {desc_escaped}</div>'

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
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
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

def write_interactive_svg(image_path, tags, description, color_style=None, font_size_style=None):
    """
    Exports a standalone interactive SVG file packaging the image (in Base64)
    with SVG rect overlays and native hover tooltips.
    """
    import base64
    import os
    try:
        # Get custom styling or defaults
        color_hex = color_style.get("hex", "#38bdf8") if color_style else "#38bdf8"
        bg_hover = color_style.get("hover", "rgba(56, 189, 248, 0.15)") if color_style else "rgba(56, 189, 248, 0.15)"

        # Determine mime-type from extension
        ext = os.path.splitext(image_path)[1].lower()
        mime_type = "image/jpeg"
        if ext == ".png":
            mime_type = "image/png"
        elif ext == ".webp":
            mime_type = "image/webp"

        # 1. Get image dimensions
        with Image.open(image_path) as img:
            width, height = img.size
            
        # 2. Read image and convert to base64
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
    <text x="{width // 2}" y="{banner_y + 24}" fill="#f1f5f9" font-family="Segoe UI, sans-serif" font-size="16" font-style="italic" text-anchor="middle">Description: {desc_escaped}</text>
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

def draw_annotations_on_image(image_path, tags, output_path, draw_names=False, color_style=None, font_size_style=None, description=None, for_editor=False):
    """
    Reads the image, draws bounding boxes and labels for each tag, and saves the result.
    - If draw_names is False (Output 2-a: Numbered): draws face bounding boxes and numbers as-is.
    - If draw_names is True (Output 2-b: Tagged v2.4): 
      i) No rectangles around faces.
      ii) Non-overlapping number badges placed on person's body (or top corner of face if body not visible).
      iii) General Photo Description and Tagged names listed in a free space footer below the photo.
    """
    try:
        import math
        from PIL import Image, ImageDraw, ImageFont
        tags = sort_faces_spatial(tags)
        with Image.open(image_path) as img:
            annotated = img.copy()
            width, height = annotated.size
            
            if annotated.mode not in ('RGB', 'RGBA'):
                annotated = annotated.convert('RGB')
                
            draw = ImageDraw.Draw(annotated, 'RGBA')
            
            line_width = max(2, int(min(width, height) / 300))
            scale_factor = font_size_style.get("scale", 1.0) if font_size_style else 1.0
            font_size = max(14, int(min(width, height) / 50 * scale_factor))
            
            box_color = color_style.get("rgb", (20, 184, 166)) if color_style else (20, 184, 166)
            box_color_rgba = box_color + (255,)
            
            font_paths = [
                "arialbd.ttf",
                "arial.ttf",
                "C:\\Windows\\Fonts\\arialbd.ttf",
                "C:\\Windows\\Fonts\\arial.ttf",
                "C:\\Windows\\Fonts\\segoeuib.ttf",
                "C:\\Windows\\Fonts\\segoeui.ttf",
                "DejaVuSans.ttf"
            ]
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
                # Output 2-a: Numbered (Kept exactly as-is)
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
                    draw.text((left + padding, text_y + padding), text, font=font, fill=(255, 255, 255, 255))
                    
                final_output_img = annotated
            else:
                # ----------------------------------------------------
                # Output 2-b: Tagged (Photo Tagger v2.3)
                # i) No face rectangles
                # ii) Number badges placed strictly OUTSIDE all face boxes
                #     - Zero face masking (NO badge inside any face bounding box)
                #     - Zero cross-person body landing
                #     - Dynamic resizing (smaller visible badge) when space is constrained
                # iii) General Photo Description and Tagged names listed in free space
                # ----------------------------------------------------
                # ----------------------------------------------------
                # Output 2-b: Tagged (Photo Tagger v2.3)
                # i) No face rectangles
                # ii) Number badges placed strictly OUTSIDE all face boxes
                #     - Zero face masking (NO badge inside any face bounding box)
                #     - Zero cross-person body landing
                #     - Dynamic resizing & pill shape for 3-digit numbers to fit inside badge
                # iii) General Photo Description and Tagged names listed in free space
                # ----------------------------------------------------
                # Use tags in the exact order passed from app/UI to guarantee 1:1 number matching!
                placed_badges = []  # List of (bx, by, badge_w, badge_h)
                
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
                    # Check overlap between badge rect [bx-bw, by-bh, bx+bw, by+bh] and box [x1, y1, x2, y2]
                    bl = bx - bw - margin
                    br = bx + bw + margin
                    bt = by - bh - margin
                    bb = by + bh + margin
                    return not (br < x1 or bl > x2 or bb < y1 or bt > y2)

                def is_valid_badge_placement(bx, by, bw, bh, person_idx):
                    # 1. Image boundary check
                    if bx - bw < 2 or bx + bw > width - 2 or by - bh < 2 or by + bh > height - 2:
                        return False

                    # 2. MUST NOT MASK ANY FACE BOX (person_idx or any other person k!)
                    for data in all_face_boxes:
                        if badge_rect_intersects_rect(bx, by, bw, bh, data['fl'], data['ft'], data['fr'], data['fb'], margin=1):
                            return False

                    # 3. MUST NOT land on ANOTHER person k's body box (k != person_idx)
                    for k, data in enumerate(all_face_boxes):
                        if k != person_idx:
                            k_body_l = data['fl'] - int(data['fw'] * 0.1)
                            k_body_r = data['fr'] + int(data['fw'] * 0.1)
                            k_body_t = data['fb'] + 1
                            k_body_b = min(height, data['fb'] + int(data['fh'] * 1.2))
                            if badge_rect_intersects_rect(bx, by, bw, bh, k_body_l, k_body_t, k_body_r, k_body_b, margin=1):
                                return False

                    # 4. MUST NOT overlap any previously placed badge
                    min_gap = 2
                    for prev_x, prev_y, prev_bw, prev_bh in placed_badges:
                        dx = abs(bx - prev_x)
                        dy = abs(by - prev_y)
                        if dx < (bw + prev_bw + min_gap) and dy < (bh + prev_bh + min_gap):
                            return False

                    return True

                # Uniform badge radius across ALL tags for identical size & shape
                scale_factor = font_size_style.get("scale", 1.0) if font_size_style else 1.0
                uniform_badge_r = max(14, int(font_size * 0.95 * scale_factor))

                for idx, t in enumerate(tags):
                    box_i = all_face_boxes[idx]
                    fl_i, ft_i, fr_i, fb_i = box_i['fl'], box_i['ft'], box_i['fr'], box_i['fb']
                    fw_i, _, cx_i, cy_i = box_i['fw'], box_i['fh'], box_i['cx'], box_i['cy']
                    
                    num_str = str(idx + 1)
                    badge_r = uniform_badge_r
                    bw = badge_r
                    bh = badge_r
                    
                    chosen_pos = None

                    # 1. Check if user set custom manual position for this badge
                    if 'bx' in t and 'by' in t and t['bx'] is not None and t['by'] is not None:
                        bx_custom = int(t['bx'] * width)
                        by_custom = int(t['by'] * height)
                        chosen_pos = (bx_custom, by_custom)
                    else:
                        # 2. Automatic smart placement search with uniform badge_r
                        candidates = [
                            (cx_i, fb_i + badge_r + 2),                 # Body below chin
                            (cx_i, ft_i - badge_r - 2),                 # Above head / hair top
                            (cx_i - int(fw_i * 0.35), ft_i - badge_r - 2), # Above head left
                            (cx_i + int(fw_i * 0.35), ft_i - badge_r - 2), # Above head right
                            (cx_i - int(fw_i * 0.35), fb_i + badge_r + 2), # Body below chin left
                            (cx_i + int(fw_i * 0.35), fb_i + badge_r + 2), # Body below chin right
                            (fl_i - badge_r - 2, cy_i),                 # Left of face box
                            (fr_i + badge_r + 2, cy_i),                 # Right of face box
                        ]
                        
                        for (cand_x, cand_y) in candidates:
                            if is_valid_badge_placement(cand_x, cand_y, bw, bh, idx):
                                chosen_pos = (cand_x, cand_y)
                                break

                        if chosen_pos is None:
                            # Outward spiral search
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

                    # Store normalized badge position in tag dict so editor and exports stay in sync
                    t['bx'] = bx / float(width)
                    t['by'] = by / float(height)

                    if not for_editor:
                        # Draw uniform circular badge on image
                        draw.ellipse([bx - badge_r, by - badge_r, bx + badge_r, by + badge_r], 
                                     fill=box_color_rgba, outline=(255, 255, 255, 255), width=max(1, line_width // 2))

                        # Draw text centered inside uniform circle with 100% uniform font size for ALL numbers
                        badge_font_size = max(9, int(badge_r * 0.72))
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
                        draw.text((tx, ty), num_str, font=badge_font, fill=(255, 255, 255, 255))
                    
                # Free space footer under photo
                if description is None:
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
                    final_output_img = Image.new('RGBA', (width, total_height), (15, 23, 42, 255))
                    final_output_img.paste(annotated, (0, 0))
                    
                    fdraw = ImageDraw.Draw(final_output_img)
                    fdraw.line([(0, height), (width, height)], fill=box_color_rgba, width=max(2, line_width))
                    
                    current_y = height + pad_top
                    
                    # Render Description Block
                    if desc_lines:
                        fdraw.text((pad_left, current_y), "PHOTO DESCRIPTION", font=legend_font, fill=box_color_rgba)
                        current_y += header_h
                        for line in desc_lines:
                            fdraw.text((pad_left, current_y), line, font=legend_font, fill=(226, 232, 240, 255))
                            current_y += line_h
                        current_y += int(line_h * 0.5)

                    # Render Tagged Persons Block
                    if num_tags > 0:
                        fdraw.text((pad_left, current_y), "TAGGED PERSONS", font=legend_font, fill=box_color_rgba)
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
                            
                            try:
                                fdraw.rounded_rectangle([x_pill, y_pill, x_pill + pill_w, y_pill + pill_h], 
                                                        radius=pill_h // 2, 
                                                        fill=box_color_rgba, 
                                                        outline=(255, 255, 255, 255), 
                                                        width=1)
                            except AttributeError:
                                fdraw.rectangle([x_pill, y_pill, x_pill + pill_w, y_pill + pill_h], 
                                                fill=box_color_rgba, 
                                                outline=(255, 255, 255, 255), 
                                                width=1)
                                
                            ptx = x_pill + (pill_w - layout['tw_n']) / 2.0 - layout['tx_off']
                            pty = y_pill + (pill_h - layout['th_n']) / 2.0 - layout['ty_off']
                            fdraw.text((ptx, pty), layout['num_str'], font=legend_font, fill=(255, 255, 255, 255))
                            
                            name_x = x_pill + pill_w + 10
                            name_color = (241, 245, 249, 255) if layout['raw_name'] else (148, 163, 184, 255)
                            total_name_h = len(layout['name_lines']) * line_spacing
                            name_y_start = y_row + (r_h - total_name_h) // 2
                            
                            for l_idx, line_txt in enumerate(layout['name_lines']):
                                line_y = name_y_start + l_idx * line_spacing
                                fdraw.text((name_x, line_y), line_txt, font=legend_font, fill=name_color)
                else:
                    final_output_img = annotated
                    
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
