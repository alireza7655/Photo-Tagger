import cv2

def merge_overlapping_boxes(boxes, threshold=0.3):
    """
    Simple Intersection-over-Union (IoU) overlap box merger.
    Merges overlapping bounding boxes to avoid double detections of the same face.
    """
    if not boxes:
        return []
    
    # Convert boxes to [x1, y1, x2, y2]
    rects = []
    for (x, y, w, h) in boxes:
        rects.append([x, y, x + w, y + h])
        
    merged = []
    while rects:
        current = rects.pop(0)
        cx1, cy1, cx2, cy2 = current
        
        has_overlap = False
        for i, other in enumerate(merged):
            ox1, oy1, ox2, oy2 = other
            
            # Intersection coordinates
            ix1 = max(cx1, ox1)
            iy1 = max(cy1, oy1)
            ix2 = min(cx2, ox2)
            iy2 = min(cy2, oy2)
            
            iw = max(0, ix2 - ix1)
            ih = max(0, iy2 - iy1)
            int_area = iw * ih
            
            # Union area
            curr_area = (cx2 - cx1) * (cy2 - cy1)
            other_area = (ox2 - ox1) * (oy2 - oy1)
            union_area = curr_area + other_area - int_area
            
            iou = int_area / union_area if union_area > 0 else 0
            
            # If overlap exceeds threshold, merge by taking union bounding box
            if iou > threshold:
                merged[i] = [
                    min(cx1, ox1),
                    min(cy1, oy1),
                    max(cx2, ox2),
                    max(cy2, oy2)
                ]
                has_overlap = True
                break
                
        if not has_overlap:
            merged.append(current)
            
    # Convert back to [x, y, w, h]
    result = []
    for [x1, y1, x2, y2] in merged:
        result.append((x1, y1, x2 - x1, y2 - y1))
    return result

def detect_faces(image_path):
    """
    Detects faces in an image using frontal and profile cascades.
    Returns a list of dicts with normalized coordinates:
    [{'name': '', 'x': center_x, 'y': center_y, 'w': width, 'h': height}, ...]
    """
    try:
        # Load image in grayscale
        img = cv2.imread(image_path)
        if img is None:
            print(f"Error: Unable to read image {image_path}")
            return []
            
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        img_h, img_w = img.shape[:2]
        
        # Load frontal and profile cascades
        frontal_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        profile_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_profileface.xml')
        
        # Detect faces
        # scaleFactor=1.1, minNeighbors=5 is standard for good accuracy
        faces_front = frontal_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
        faces_profile = profile_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
        
        # Gather all detections
        all_boxes = []
        if len(faces_front) > 0:
            for (x, y, w, h) in faces_front:
                all_boxes.append((x, y, w, h))
        if len(faces_profile) > 0:
            for (x, y, w, h) in faces_profile:
                all_boxes.append((x, y, w, h))
                
        # Merge overlapping boxes
        merged_boxes = merge_overlapping_boxes(all_boxes)
        
        # Convert to normalized coordinates relative to image size
        normalized_faces = []
        for (x, y, w, h) in merged_boxes:
            cx = (x + w / 2.0) / img_w
            cy = (y + h / 2.0) / img_h
            nw = w / img_w
            nh = h / img_h
            normalized_faces.append({
                'name': '',
                'x': cx,
                'y': cy,
                'w': nw,
                'h': nh
            })
            
        return normalized_faces
    except Exception as e:
        print(f"Error during face detection on {image_path}: {e}")
        return []
