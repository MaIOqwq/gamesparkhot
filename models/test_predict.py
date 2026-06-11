#!/usr/bin/env python3
"""Test the 5-class model prediction"""
import json, urllib.request

# Test with a keyword that should have data
keywords = ['原神', '王者荣耀', '和平精英']

for kw in keywords:
    url = f'http://localhost:5000/api/predict/trend?keyword={urllib.request.quote(kw)}'
    try:
        resp = urllib.request.urlopen(url, timeout=10)
        data = json.loads(resp.read())
        print(f'{kw}: code={data["code"]}, model={data["data"].get("model","?")}, trend={data["data"]["trend"]}, prob={data["data"]["probability"]}')
    except Exception as e:
        print(f'{kw}: ERROR {e}')
