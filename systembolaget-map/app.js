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
    initialize: function (stores, opts) {
      this._stores = stores;
      // Precompute flat coordinate arrays for the hot loop.
      this._lat = new Float64Array(stores.length);
      this._lon = new Float64Array(stores.length);
      for (var i = 0; i < stores.length; i++) {
        this._lat[i] = stores[i].lat;
        this._lon[i] = stores[i].lon;
      }
      this._cell = (opts && opts.cell) || 6; // CSS px per sampled cell
      this._maxDist = (opts && opts.maxDist) || 50; // km mapped to full red
      this._alpha = (opts && opts.alpha) || 0.55;
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

  function init(data) {
    var stores = data.stores;

    var map = L.map("map", { zoomControl: true, minZoom: 4, maxZoom: 14 });
    map.setView([62.5, 16.5], 5); // Sweden, replaced by fitBounds below

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

    // Store markers
    var markers = L.layerGroup();
    stores.forEach(function (s) {
      var m = L.circleMarker([s.lat, s.lon], {
        radius: 3,
        color: "#1b1b1b",
        weight: 1,
        fillColor: "#ffffff",
        fillOpacity: 0.9,
      });
      var addr = [s.address, s.city].filter(Boolean).join(", ");
      m.bindPopup(
        '<div class="store-popup"><b>' +
          escapeHtml(s.name) +
          "</b><br><span class=\"meta\">" +
          escapeHtml(addr) +
          (s.county ? "<br>" + escapeHtml(s.county) : "") +
          "</span></div>"
      );
      markers.addLayer(m);
    });
    markers.addTo(map);

    // Frame all of Sweden from the store extent.
    var bounds = L.latLngBounds(stores.map(function (s) {
      return [s.lat, s.lon];
    }));
    map.fitBounds(bounds, { padding: [20, 20] });

    // Click to measure distance to nearest store.
    map.on("click", function (e) {
      var res = distLayer.nearest(e.latlng);
      L.popup({ className: "dist-popup-wrap" })
        .setLatLng(e.latlng)
        .setContent(
          '<div class="dist-popup"><span class="km">' +
            res.dist.toFixed(1) +
            " km</span><br><span class=\"near\">to nearest store:<br><b>" +
            escapeHtml(res.store.name) +
            "</b>" +
            (res.store.city ? " (" + escapeHtml(res.store.city) + ")" : "") +
            "</span></div>"
        )
        .openOn(map);
    });

    wireControls(map, distLayer, markers, stores.length);
  }

  function wireControls(map, distLayer, markers, count) {
    document.getElementById("store-count").textContent =
      count + " stores.";

    document.getElementById("toggle-overlay").addEventListener("change", function (e) {
      if (e.target.checked) distLayer.addTo(map);
      else map.removeLayer(distLayer);
    });

    document.getElementById("toggle-stores").addEventListener("change", function (e) {
      if (e.target.checked) markers.addTo(map);
      else map.removeLayer(markers);
    });

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

  fetch("data/stores.json")
    .then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(init)
    .catch(function (err) {
      document.getElementById("map").innerHTML =
        '<p style="padding:2rem;font-family:sans-serif">Failed to load store data: ' +
        escapeHtml(err.message) +
        "</p>";
    });
})();
