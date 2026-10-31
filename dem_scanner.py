import os
import argparse
import numpy as np
try:
    import rasterio
    from rasterio.plot import show
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
except ImportError:
    print("🚨 请先安装依赖: pip install rasterio matplotlib numpy")
    exit()

# ==========================================
# 模块 1：本地 TIF 高程图“X光”扫描诊断
# ==========================================
def scan_local_dem(tif_path, output_file=None, show_plot=True):
    print(f"\n🔍 [GIS 诊断室] 正在对高程图进行 X 光扫描: {tif_path}")
    if not os.path.exists(tif_path):
        print(f"❌ 找不到文件: {tif_path}")
        return

    with rasterio.open(tif_path) as src:
        dem_data = src.read(1).astype(np.float32)
        bounds = src.bounds
        nodata_val = src.nodata

        print("\n📊 [雷达元数据]")
        print(f"  - 经纬度边界: 左下({bounds.left:.4f}, {bounds.bottom:.4f}) -> 右上({bounds.right:.4f}, {bounds.top:.4f})")
        print(f"  - 矩阵分辨率: {src.width} x {src.height} 像素")
        print(f"  - 官方空值标记 (NODATA): {nodata_val}")

        # 统计物理黑洞
        total_pixels = src.width * src.height
        
        # Use the raster's validity mask. Sea level, below-sea-level terrain,
        # and other legitimate non-positive elevations must remain valid.
        void_mask = src.read_masks(1) == 0

        void_pixels = np.sum(void_mask)
        valid_pixels = total_pixels - void_pixels
        health_rate = (valid_pixels / total_pixels) * 100

        print("\n🩺 [完整度体检报告]")
        print(f"  - 总采样点: {total_pixels:,} 个")
        print(f"  - 有效地形: {valid_pixels:,} 个")
        print(f"  - 雷达空洞: {void_pixels:,} 个 (包含 0 米或无法探测的深谷)")
        
        if health_rate < 95.0:
            print(f"  - ⚠️ 战区完整度: {health_rate:.2f}% (警告：存在严重的情报断层！)")
        else:
            print(f"  - ✅ 战区完整度: {health_rate:.2f}% (健康，可用于精确制导与行军)")

        # 渲染 X 光诊断图
        print("\n🎨 正在生成战区病灶可视化图像...")
        
        # 创建一个掩码数组用于绘图，将空洞设为 NaN
        plot_data = np.where(void_mask, np.nan, dem_data)
        
        fig, ax = plt.subplots(figsize=(10, 8))
        ax.set_title(f"DEM X-Ray Scan (Health: {health_rate:.2f}%) \nRed areas are Data Voids (0m or NoData)")
        
        # 绘制正常地形（使用地形色带）
        im = ax.imshow(plot_data, cmap='terrain', extent=[bounds.left, bounds.right, bounds.bottom, bounds.top])
        
        # 用鲜红色绘制空洞区域！
        cmap_red = ListedColormap(['red'])
        ax.imshow(void_mask, cmap=cmap_red, alpha=np.where(void_mask, 1.0, 0.0), extent=[bounds.left, bounds.right, bounds.bottom, bounds.top])
        
        plt.colorbar(im, ax=ax, label='Elevation (meters)')
        plt.xlabel('Longitude')
        plt.ylabel('Latitude')
        if output_file:
            fig.savefig(output_file, dpi=150, bbox_inches="tight")
            print(f"✅ 诊断图已保存至: {output_file}")
        if show_plot:
            plt.show()
        else:
            plt.close(fig)

def build_parser():
    parser = argparse.ArgumentParser(
        description="Inspect a locally supplied GeoTIFF whose commercial-use and redistribution rights have been approved."
    )
    parser.add_argument("tif_path")
    parser.add_argument("--output", help="Save the diagnostic image")
    parser.add_argument("--no-show", action="store_true")
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    scan_local_dem(args.tif_path, output_file=args.output, show_plot=not args.no_show)
