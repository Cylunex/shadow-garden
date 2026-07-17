/* 地图助手：基于自托管 Leaflet（assets/vendor/leaflet）。
   瓦片源统一在这里配置；国内访问 OSM 慢的话，换下面两行即可。 */
window.GardenMap = (function () {
  var TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
  var TILE_ATTR = '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>';

  function create(el, opts) {
    opts = opts || {};
    var map = L.map(el, {
      scrollWheelZoom: opts.scrollWheelZoom === undefined ? false : opts.scrollWheelZoom,
      center: opts.center || [35.5, 105],   // 默认中国全图
      zoom: opts.zoom || 4,
    });
    L.tileLayer(TILE_URL, { maxZoom: 19, attribution: TILE_ATTR }).addTo(map);
    return map;
  }

  /* points: [{lat, lng, html}]；自动缩放到覆盖所有点 */
  function markers(map, points) {
    var latlngs = [];
    points.forEach(function (p) {
      var m = L.marker([p.lat, p.lng]).addTo(map);
      if (p.html) m.bindPopup(p.html);
      latlngs.push([p.lat, p.lng]);
    });
    if (latlngs.length === 1) map.setView(latlngs[0], 11);
    else if (latlngs.length > 1) map.fitBounds(L.latLngBounds(latlngs).pad(0.25));
    return latlngs.length;
  }

  return { create: create, markers: markers };
})();
