import json, os
for f in sorted(os.listdir('here')):
    if f.endswith('.geojson'):
        with open(os.path.join('here', f), encoding='utf-8') as fh:
            data = json.load(fh)
            feats = data.get('features', [])
            print(f"{f}: {len(feats)} features")
            if feats:
                props = feats[0].get('properties', {})
                keys = list(props.keys())[:10]
                print(f"  Keys: {keys}")
                geom = feats[0].get('geometry', {})
                gtype = geom.get('type', '?')
                coords = geom.get('coordinates', [])
                print(f"  Geom: {gtype} -> {str(coords)[:60]}")
                # Show a sample name
                name = props.get('name', props.get('Name', 'N/A'))
                print(f"  Sample: {name}")
                print()
