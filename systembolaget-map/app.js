/* Distance-to-nearest-Systembolaget interactive map.
 *
 * - Base map: CartoDB Positron tiles.
 * - Distance overlay: a custom canvas layer that, for a grid of screen cells,
 *   computes the great-circle distance to the nearest store and paints it on a
 *   green→red colormap. Recomputed whenever the map settles (moveend/resize).
 * - Store markers + click-to-measure.
 *
 * Data: data/stores.json, produced by fetch_stores.py.
 */

(function () {
  "use strict";

  var EARTH_R = 6371; // km
  var DEG2RAD = Math.PI / 180;

  // --- helpers --------------------------------------------------------------

  function haversine(lat1, lon1, lat2, lon2) {
    var dlat = (lat2 - lat1) * DEG2RAD;
    var dlon = (lon2 - lon1) * DEG2RAD;
    var a =
      Math.sin(dlat / 2) * Math.sin(dlat / 2) +
      Math.cos(lat1 * DEG2RAD) * Math.cos(lat2 * DEG2RAD) *
        Math.sin(dlon / 2) * Math.sin(dlon / 2);
    return 2 * EARTH_R * Math.asin(Math.min(1, Math.sqrt(a)));
  }

  // hue 140 (green) -> 0 (red); kept in sync with the legend gradient in CSS.
  function colorFor(t) {
    var hue = 140 * (1 - t);
    return "hsl(" + hue.toFixed(0) + ", 80%, 50%)";
  }

  // --- distance overlay layer ----------------------------------------------

  var DistanceLayer = L.Layer.extend({
    initialize: function (points, opts) {
      this._setPoints(points);
      this._cell = (opts && opts.cell) || 6; // CSS px per sampled cell
      this._maxDist = (opts && opts.maxDist) || 50; // km mapped to full red
      this._alpha = (opts && opts.alpha) || 0.55;
    },

    // Replace the point set the overlay measures distance to, then redraw.
    _setPoints: function (points) {
      this._stores = points;
      // Precompute flat coordinate arrays for the hot loop.
      this._lat = new Float64Array(points.length);
      this._lon = new Float64Array(points.length);
      for (var i = 0; i < points.length; i++) {
        this._lat[i] = points[i].lat;
        this._lon[i] = points[i].lon;
      }
    },

    setPoints: function (points) {
      this._setPoints(points);
      if (this._map) this._draw();
    },

    setMaxDist: function (km) {
      this._maxDist = km;
      this._draw();
    },

    onAdd: function (map) {
      this._map = map;
      var canvas = (this._canvas = L.DomUtil.create("canvas", "leaflet-layer"));
      canvas.style.pointerEvents = "none";
      var size = map.getSize();
      canvas.width = size.x;
      canvas.height = size.y;
      map.getPanes().overlayPane.appendChild(canvas);

      map.on("moveend", this._reset, this);
      map.on("resize", this._resize, this);
      map.on("movestart zoomstart", this._hide, this);

      this._reset();
    },

    onRemove: function (map) {
      L.DomUtil.remove(this._canvas);
      map.off("moveend", this._reset, this);
      map.off("resize", this._resize, this);
      map.off("movestart zoomstart", this._hide, this);
    },

    _hide: function () {
      this._canvas.style.opacity = "0";
    },

    _resize: function () {
      var size = this._map.getSize();
      this._canvas.width = size.x;
      this._canvas.height = size.y;
      this._reset();
    },

    _reset: function () {
      // Pin the canvas to the current top-left, then draw in container-pixel space.
      var topLeft = this._map.containerPointToLayerPoint([0, 0]);
      L.DomUtil.setPosition(this._canvas, topLeft);
      this._draw();
    },

    _draw: function () {
      var map = this._map;
      var canvas = this._canvas;
      var ctx = canvas.getContext("2d");
      var w = canvas.width;
      var h = canvas.height;
      ctx.clearRect(0, 0, w, h);

      var cell = this._cell;
      var lat = this._lat;
      var lon = this._lon;
      var n = lat.length;
      var maxDist = this._maxDist;
      var alpha = this._alpha;

      ctx.globalAlpha = alpha;

      for (var py = 0; py < h; py += cell) {
        for (var px = 0; px < w; px += cell) {
          // Sample at the centre of the cell.
          var ll = map.containerPointToLatLng([px + cell / 2, py + cell / 2]);
          var clat = ll.lat;
          var clon = ll.lng;

          var best = Infinity;
          for (var i = 0; i < n; i++) {
            var d = haversine(clat, clon, lat[i], lon[i]);
            if (d < best) best = d;
          }

          var t = best / maxDist;
          if (t > 1) t = 1;
          else if (t < 0) t = 0;
          ctx.fillStyle = colorFor(t);
          ctx.fillRect(px, py, cell, cell);
        }
      }

      ctx.globalAlpha = 1;
      canvas.style.opacity = "1";
    },

    nearest: function (latlng) {
      var lat = this._lat;
      var lon = this._lon;
      var best = Infinity;
      var idx = -1;
      for (var i = 0; i < lat.length; i++) {
        var d = haversine(latlng.lat, latlng.lng, lat[i], lon[i]);
        if (d < best) {
          best = d;
          idx = i;
        }
      }
      return { dist: best, store: this._stores[idx] };
    },
  });

  // --- bootstrap ------------------------------------------------------------

  // Build the Gothenburg drive-time boundaries as a feature group: each
  // isochrone is drawn as a white-cased coloured outline (no fill, so the
  // distance overlay shows through), plus a label and the origin marker.
  function buildIsochrones(iso) {
    var fg = L.featureGroup();
    if (!iso || !iso.features) return fg;

    var styles = {
      60: { color: "#1d4ed8", dash: null, label: "1 h drive" },
      120: { color: "#7c3aed", dash: "8 7", label: "2 h drive" },
    };

    var polys = iso.features.filter(function (f) {
      return f.geometry && f.geometry.type === "Polygon";
    });
    // Draw the larger (2h) ring first so the 1h ring sits on top.
    polys.sort(function (a, b) {
      return (b.properties.minutes || 0) - (a.properties.minutes || 0);
    });

    polys.forEach(function (f) {
      var ring = f.geometry.coordinates[0].map(function (c) {
        return [c[1], c[0]]; // [lon,lat] -> [lat,lng]
      });
      var st = styles[f.properties.minutes] || { color: "#333", dash: null, label: "" };

      // White casing underneath for contrast against the colour overlay.
      L.polygon(ring, {
        fill: false, color: "#ffffff", weight: 6, opacity: 0.9,
      }).addTo(fg);

      var line = L.polygon(ring, {
        fill: false, color: st.color, weight: 3, opacity: 1, dashArray: st.dash,
      }).addTo(fg);
      line.bindTooltip(
        (f.properties.label || st.label),
        { sticky: true }
      );

      // Permanent label at the northernmost vertex of the ring.
      var north = ring.reduce(function (best, p) {
        return p[0] > best[0] ? p : best;
      }, ring[0]);
      L.marker(north, {
        interactive: false,
        icon: L.divIcon({
          className: "iso-label",
          html: '<span style="background:' + st.color + '">' + st.label + "</span>",
          iconSize: null,
        }),
      }).addTo(fg);
    });

    // Gothenburg origin marker.
    var o = iso.origin;
    if (o) {
      L.circleMarker([o.lat, o.lon], {
        radius: 7, color: "#ffffff", weight: 2,
        fillColor: "#d11", fillOpacity: 1,
      })
        .bindTooltip(o.name, { permanent: true, direction: "right", className: "origin-label" })
        .addTo(fg);
    }

    return fg;
  }

  function init(data, iso) {
    var stores = data.stores;
    var ombud = data.ombud || [];
    // Tag each record so click-to-measure can name the kind of the nearest point.
    stores.forEach(function (s) { s.kind = "store"; });
    ombud.forEach(function (o) { o.kind = "ombud"; });

    var map = L.map("map", { zoomControl: false, minZoom: 4, maxZoom: 14 });
    // Bottom-right so the controls never sit behind the panel on mobile.
    L.control.zoom({ position: "bottomright" }).addTo(map);
    map.setView([57.7089, 11.9746], 8); // Gothenburg, replaced by fitBounds below

    L.tileLayer(
      "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
      {
        attribution:
          '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> ' +
          'contributors &copy; <a href="https://carto.com/attributions">CARTO</a> · ' +
          "Store data: Systembolaget",
        subdomains: "abcd",
        maxZoom: 20,
      }
    ).addTo(map);

    // Distance overlay
    var distLayer = new DistanceLayer(stores, { cell: 6, maxDist: 50 });
    distLayer.addTo(map);

    // Marker layers. Stores are the white-on-black dots that feed the distance
    // overlay; ombud (third-party agents / pickup points) are a separate amber
    // layer, off by default.
    function markerLayer(list, style, kind) {
      var group = L.layerGroup();
      list.forEach(function (s) {
        var m = L.circleMarker([s.lat, s.lon], style);
        var addr = [s.address, s.city].filter(Boolean).join(", ");
        m.bindPopup(
          '<div class="store-popup"><b>' +
            escapeHtml(s.name) +
            '</b>' + (kind ? ' <span class="kind">' + kind + "</span>" : "") +
            "<br><span class=\"meta\">" +
            escapeHtml(addr) +
            (s.county ? "<br>" + escapeHtml(s.county) : "") +
            "</span></div>"
        );
        group.addLayer(m);
      });
      return group;
    }

    var markers = markerLayer(stores, {
      radius: 3, color: "#1b1b1b", weight: 1,
      fillColor: "#ffffff", fillOpacity: 0.9,
    });
    markers.addTo(map);

    // Hollow rings (no fill) so the ~445 ombud mark their spots without
    // washing colour over the distance overlay underneath.
    var ombudMarkers = markerLayer(ombud, {
      radius: 3, color: "#b35c00", weight: 1.6,
      fill: false, opacity: 0.95,
    }, "ombud");
    // Off by default — there are ~445 of them and they'd clutter the view.

    // Drive-time isochrones from Gothenburg (1h / 2h), drawn as boundaries on
    // top of the distance overlay.
    var isoLayer = buildIsochrones(iso);
    isoLayer.addTo(map);

    // Frame the Gothenburg vicinity: fit to the 2h drive-time extent.
    var isoBounds = isoLayer.getBounds && isoLayer.getBounds();
    if (isoBounds && isoBounds.isValid()) {
      map.fitBounds(isoBounds, { padding: [40, 40] });
    } else {
      map.fitBounds(
        L.latLngBounds(stores.map(function (s) { return [s.lat, s.lon]; })),
        { padding: [20, 20] }
      );
    }

    // Click to measure distance to the nearest point the overlay is measuring
    // (stores, or stores + ombud when the ombud layer is on).
    map.on("click", function (e) {
      var res = distLayer.nearest(e.latlng);
      L.popup({ className: "dist-popup-wrap" })
        .setLatLng(e.latlng)
        .setContent(
          '<div class="dist-popup"><span class="km">' +
            res.dist.toFixed(1) +
            " km</span><br><span class=\"near\">to nearest " +
            (res.store.kind === "ombud" ? "ombud" : "store") +
            ":<br><b>" +
            escapeHtml(res.store.name) +
            "</b>" +
            (res.store.city ? " (" + escapeHtml(res.store.city) + ")" : "") +
            "</span></div>"
        )
        .openOn(map);
    });

    wireControls(map, distLayer, markers, ombudMarkers, isoLayer, stores, ombud);
  }

  function wireControls(map, distLayer, markers, ombudMarkers, isoLayer, stores, ombud) {
    document.getElementById("store-count").textContent =
      stores.length + " stores, " + ombud.length + " ombud.";

    document.getElementById("toggle-overlay").addEventListener("change", function (e) {
      if (e.target.checked) distLayer.addTo(map);
      else map.removeLayer(distLayer);
    });

    document.getElementById("toggle-stores").addEventListener("change", function (e) {
      if (e.target.checked) markers.addTo(map);
      else map.removeLayer(markers);
    });

    document.getElementById("toggle-ombud").addEventListener("change", function (e) {
      if (e.target.checked) {
        ombudMarkers.addTo(map);
        // Overlay now measures distance to the nearest store OR ombud.
        distLayer.setPoints(stores.concat(ombud));
      } else {
        map.removeLayer(ombudMarkers);
        distLayer.setPoints(stores); // back to nearest store only
      }
    });

    document.getElementById("toggle-iso").addEventListener("change", function (e) {
      if (e.target.checked) isoLayer.addTo(map);
      else map.removeLayer(isoLayer);
    });

    var focusBtn = document.getElementById("focus-gbg");
    if (focusBtn) {
      focusBtn.addEventListener("click", function () {
        var b = isoLayer.getBounds && isoLayer.getBounds();
        if (b && b.isValid()) map.fitBounds(b, { padding: [40, 40] });
      });
    }

    var slider = document.getElementById("max-dist");
    var label = document.getElementById("max-dist-label");
    var legendMid = document.getElementById("legend-mid");
    var legendMax = document.getElementById("legend-max");
    slider.addEventListener("input", function (e) {
      var km = +e.target.value;
      label.textContent = km;
      legendMid.textContent = (km / 2).toFixed(0);
      legendMax.textContent = km + "+ km";
      distLayer.setMaxDist(km);
    });
  }

  function escapeHtml(str) {
    return String(str == null ? "" : str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // --- load data ------------------------------------------------------------

  // Collapsible control panel — keeps the map usable on small screens.
  (function setupPanelToggle() {
    var panel = document.getElementById("panel");
    var btn = document.getElementById("panel-toggle");
    if (!panel || !btn) return;

    function setCollapsed(collapsed) {
      panel.classList.toggle("collapsed", collapsed);
      btn.setAttribute("aria-expanded", String(!collapsed));
    }

    btn.addEventListener("click", function () {
      setCollapsed(!panel.classList.contains("collapsed"));
    });

    // Start collapsed on narrow (mobile) screens so the panel doesn't cover the map.
    if (window.matchMedia("(max-width: 520px)").matches) {
      setCollapsed(true);
    }
  })();

  function loadJson(url) {
    return fetch(url).then(function (r) {
      if (!r.ok) throw new Error(url + ": HTTP " + r.status);
      return r.json();
    });
  }

  Promise.all([loadJson("data/stores.json"), loadJson("data/isochrones.json")])
    .then(function (res) {
      init(res[0], res[1]);
    })
    .catch(function (err) {
      document.getElementById("map").innerHTML =
        '<p style="padding:2rem;font-family:sans-serif">Failed to load store data: ' +
        escapeHtml(err.message) +
        "</p>";
    });
})();
