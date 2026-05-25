import xml.etree.ElementTree as ET
import re
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
                return metadata

            # 3. Read general description from XMP dc:description if not found in EXIF
            if not metadata['description']:
                dc_desc = root.find('.//{http://purl.org/dc/elements/1.1/}description')
                if dc_desc is not None:
                    # Look for rdf:Alt and rdf:li
                    li = dc_desc.find('.//{http://www.w3.org/1999/02/22-rdf-syntax-ns#}li')
                    if li is not None and li.text:
                        metadata['description'] = li.text.strip()

            # 4. Read face regions
            # Try MWG regions first
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
                        return metadata

            # If no MWG regions, try Microsoft RegionInfo
            mp_region_info = root.find('.//{http://ns.microsoft.com/photo/1.2/}RegionInfo')
            if mp_region_info is not None:
                regions = mp_region_info.find('.//{http://ns.microsoft.com/photo/1.2/t/RegionInfo#}Regions')
                if regions is not None:
                    for li in regions.findall('.//{http://www.w3.org/1999/02/22-rdf-syntax-ns#}li'):
                        # Check for nested Description tag (standard Microsoft format)
                        desc_el = li.find('{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Description')
                        source = desc_el if desc_el is not None else li
                        
                        name = source.get('{http://ns.microsoft.com/photo/1.2/t/Region#}PersonDisplayName') or ""
                        rect_str = source.get('{http://ns.microsoft.com/photo/1.2/t/Region#}Rectangle') or ""
                        if rect_str:
                            try:
                                # left, top, width, height
                                left, top, w, h = map(float, rect_str.split(','))
                                x = left + w / 2.0
                                y = top + h / 2.0
                                metadata['tags'].append({'name': name, 'x': x, 'y': y, 'w': w, 'h': h})
                            except Exception as e:
                                print(f"Error parsing Microsoft region rectangle: {rect_str}: {e}")
    except Exception as e:
        print(f"Error reading metadata from {image_path}: {e}")
        
    return metadata

def write_photo_metadata(image_path, tags, description):
    """
    Writes face regions (MWG & Microsoft format) and description (EXIF & XMP) back to the JPEG.
    """
    try:
        # Load the original image first
        with Image.open(image_path) as img:
            width, height = img.size
            existing_xmp_bytes = img.info.get("xmp")
            exif = img.getexif() or Image.Exif()
            
            # Keep original saving parameters to maintain quality
            save_params = {
                'format': 'JPEG',
                'exif': exif
            }
            if 'quality' in img.info:
                save_params['quality'] = img.info['quality']
            else:
                save_params['quality'] = 95
            if 'subsampling' in img.info:
                save_params['subsampling'] = img.info['subsampling']
            
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

            # Update EXIF description (tag 270)
            if description:
                exif[270] = description.strip()
                # Update XMP dc:description
                dc_desc = ET.SubElement(desc, '{http://purl.org/dc/elements/1.1/}description')
                alt = ET.SubElement(dc_desc, '{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Alt')
                li = ET.SubElement(alt, '{http://www.w3.org/1999/02/22-rdf-syntax-ns#}li', {
                    '{http://www.w3.org/XML/1998/namespace}lang': 'x-default'
                })
                li.text = description.strip()
            else:
                if 270 in exif:
                    del exif[270]

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
                    
                    # Create the li element
                    li = ET.SubElement(mp_bag, '{http://www.w3.org/1999/02/22-rdf-syntax-ns#}li')
                    # Create nested rdf:Description inside the li element (strict MS schema)
                    ET.SubElement(li, '{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Description', {
                        '{http://ns.microsoft.com/photo/1.2/t/Region#}Rectangle': rect_str,
                        '{http://ns.microsoft.com/photo/1.2/t/Region#}PersonDisplayName': str(t['name']) if t['name'] is not None else ""
                    })

            # Serialize XMP block
            xml_str = ET.tostring(root, encoding='utf-8').decode('utf-8')
            packet = f'<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>\n{xml_str}\n<?xpacket end="w"?>'
            
            # Save the image with new exif and xmp
            # Pillow modifies the file in place or to a temp file, we can write to a temporary path and then swap,
            # or just load into memory, delete file/truncate, and rewrite to prevent lock/sharing issues.
            # To be safest, we save to a new temporary file in the same directory, then replace.
            temp_path = image_path + ".tmp"
            
            img.save(temp_path, xmp=packet.encode('utf-8'), **save_params)
            
        # Replace original with the newly tagged file
        import os
        if os.path.exists(temp_path):
            if os.path.exists(image_path):
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

def write_interactive_html(image_path, tags, description):
    """
    Exports a standalone interactive HTML file packaging the JPEG image (in Base64)
    with CSS-styled hover overlays and tooltips.
    """
    import base64
    import os
    try:
        # 1. Read JPEG and convert to base64
        with open(image_path, "rb") as f:
            b64_data = base64.b64encode(f.read()).decode("utf-8")
            
        # 2. Build face tag overlays
        tags_html = ""
        for t in tags:
            # Map normalized center coordinates to top-left percentages
            left = max(0.0, min(100.0, (t['x'] - t['w'] / 2.0) * 100.0))
            top = max(0.0, min(100.0, (t['y'] - t['h'] / 2.0) * 100.0))
            w = max(0.0, min(100.0 - left, t['w'] * 100.0))
            h = max(0.0, min(100.0 - top, t['h'] * 100.0))
            
            name = t['name'].strip() if t['name'] else "Unnamed"
            
            tags_html += f"""
        <div class="face-tag" style="left: {left:.2f}%; top: {top:.2f}%; width: {w:.2f}%; height: {h:.2f}%;">
            <div class="tooltip">{name}</div>
        </div>"""

        # Description banner HTML
        desc_banner_html = ""
        if description:
            desc_banner_html = f'<div class="description-banner">Description: {description}</div>'

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
            border-color: #38bdf8;
            box-shadow: 0 0 12px rgba(56, 189, 248, 0.6);
            background-color: rgba(56, 189, 248, 0.1);
        }}
        .tooltip {{
            position: absolute;
            bottom: calc(100% + 8px);
            left: 50%;
            transform: translateX(-50%) scale(0.95);
            background-color: #2563eb;
            color: white;
            padding: 6px 12px;
            border-radius: 6px;
            font-size: 13px;
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
            border-color: #2563eb transparent transparent transparent;
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
        <img src="data:image/jpeg;base64,{b64_data}" alt="Tagged Photo">
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

def write_interactive_svg(image_path, tags, description):
    """
    Exports a standalone interactive SVG file packaging the JPEG image (in Base64)
    with SVG rect overlays and native hover tooltips.
    """
    import base64
    import os
    try:
        # 1. Get image dimensions
        with Image.open(image_path) as img:
            width, height = img.size
            
        # 2. Read JPEG and convert to base64
        with open(image_path, "rb") as f:
            b64_data = base64.b64encode(f.read()).decode("utf-8")
            
        # 3. Build face tag overlays in SVG rects
        rects_svg = ""
        for t in tags:
            # Map normalized center coordinates to absolute pixel coordinates
            left = (t['x'] - t['w'] / 2.0) * width
            top = (t['y'] - t['h'] / 2.0) * height
            w = t['w'] * width
            h = t['h'] * height
            
            name = t['name'].strip() if t['name'] else "Unnamed"
            
            rects_svg += f"""
  <rect class="face-box" x="{left:.1f}" y="{top:.1f}" width="{w:.1f}" height="{h:.1f}">
    <title>{name}</title>
  </rect>"""

        # Description banner in SVG
        desc_banner_svg = ""
        if description:
            banner_h = 40
            banner_y = height - banner_h
            desc_banner_svg = f"""
  <g class="desc-banner">
    <rect x="0" y="{banner_y}" width="{width}" height="{banner_h}" fill="#1e293b" fill-opacity="0.85" />
    <text x="{width // 2}" y="{banner_y + 24}" fill="#f1f5f9" font-family="Segoe UI, sans-serif" font-size="16" font-style="italic" text-anchor="middle">Description: {description}</text>
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
      stroke: #38bdf8;
      fill: rgba(56, 189, 248, 0.15);
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
  <image href="data:image/jpeg;base64,{b64_data}" x="0" y="0" width="{width}" height="{height}" />
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
