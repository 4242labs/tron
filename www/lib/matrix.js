(function () {
  var mc = document.getElementById("matrix-canvas");
  if (!mc) return;
  var mctx = mc.getContext("2d");

  function resize() {
    mc.width = window.innerWidth;
    mc.height = window.innerHeight;
  }
  resize();
  window.addEventListener("resize", resize);

  var fontSize = 14;
  var columns = Math.floor(mc.width / fontSize);
  var drops = [];
  for (var i = 0; i < columns; i++) {
    drops[i] = Math.random() * -100;
  }

  var chars = "0123456789";

  function draw() {
    // Semi-transparent black to create fade trail
    mctx.fillStyle = "rgba(0, 0, 0, 0.06)";
    mctx.fillRect(0, 0, mc.width, mc.height);

    mctx.font = fontSize + "px monospace";

    // Recalculate columns on each frame in case of resize
    var currentCols = Math.floor(mc.width / fontSize);
    while (drops.length < currentCols) {
      drops.push(Math.random() * -100);
    }

    for (var i = 0; i < currentCols; i++) {
      // Speed: edges slow (0.3), center fast (1.5)
      var ratio = i / (currentCols - 1 || 1);
      var centerness = 1 - Math.abs(ratio - 0.5) * 2;
      var speed = 0.15 + centerness * 0.6;

      var char = chars[Math.floor(Math.random() * chars.length)];
      var x = i * fontSize;
      var y = drops[i] * fontSize;

      // Trail: 42labs DS --mint #00FFA7 at low alpha
      var alpha = 0.15 + Math.random() * 0.1;
      mctx.fillStyle = "rgba(0, 255, 167, " + alpha + ")";
      mctx.fillText(char, x, y);

      // Lead char: --off-white #F2F4F5 at 0.5 alpha (brighter than trail)
      if (Math.random() > 0.97) {
        mctx.fillStyle = "rgba(242, 244, 245, 0.5)";
        mctx.fillText(char, x, y);
      }

      // Reset drop to top when it goes off screen, with randomness
      if (y > mc.height && Math.random() > 0.975) {
        drops[i] = 0;
      }
      drops[i] += speed;
    }

    requestAnimationFrame(draw);
  }

  draw();
})();
