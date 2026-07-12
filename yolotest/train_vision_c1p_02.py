"""Train Vision_C1P_02 — merged dataset (old manual + new auto-labeled)."""
import os
import yaml
import shutil
from ultralytics import YOLO


def main():
    DATASET = r"D:\gammasoftware\GameLens\modelveri\Is_subtittle-.v1c-v2.yolov11_merged"
    DATA_YAML = os.path.join(DATASET, "data.yaml")

    with open(DATA_YAML, 'r') as f:
        config = yaml.safe_load(f)
    config['train'] = os.path.join(DATASET, "train", "images")
    config['val'] = os.path.join(DATASET, "val", "images")
    config['test'] = os.path.join(DATASET, "test", "images")

    fixed_yaml = os.path.join(DATASET, "data_fixed.yaml")
    with open(fixed_yaml, 'w') as f:
        yaml.dump(config, f)

    print(f"Dataset: {DATASET}")
    print(f"Train: {len(os.listdir(config['train']))} images")
    print(f"Val:   {len(os.listdir(config['val']))} images")
    print(f"Test:  {len(os.listdir(config['test']))} images")
    print(f"Classes: nc={config['nc']}, names={config['names']}")

    model = YOLO("yolo26n.pt")

    results = model.train(
        data=fixed_yaml,
        epochs=100,
        imgsz=512,
        batch=32,
        device=0,
        workers=2,
        name="Vision_C1P_02",
        project=r"D:\gammasoftware\GameLens\yolotest\runs",
        exist_ok=True,
        patience=25,
        save=True,
        save_period=10,
        cos_lr=True,
        warmup_epochs=5,
        lr0=0.001,
        lrf=0.0001,
        momentum=0.937,
        weight_decay=0.0005,
        augment=True,
        hsv_h=0.015,
        hsv_s=0.7,
        hsv_v=0.4,
        degrees=5.0,
        translate=0.1,
        scale=0.5,
        shear=0.0,
        perspective=0.0,
        flipud=0.0,
        fliplr=0.0,
        mosaic=1.0,
        mixup=0.1,
        copy_paste=0.1,
    )

    best_pt = os.path.join(results.save_dir, "weights", "best.pt")
    print(f"\nBest model: {best_pt}")

    print("\nExporting to ONNX...")
    best_model = YOLO(best_pt)
    best_model.export(format="onnx", imgsz=512, device=0, opset=12, simplify=True)

    dst = r"D:\gammasoftware\GameLens\models\Vision_C1P_02.pt"
    shutil.copy2(best_pt, dst)
    print(f"Copied to: {dst}")

    dst_onnx = r"D:\gammasoftware\GameLens\models\Vision_C1P_02.onnx"
    onnx_src = best_pt.replace('.pt', '.onnx')
    if os.path.exists(onnx_src):
        shutil.copy2(onnx_src, dst_onnx)
        print(f"ONNX copied to: {dst_onnx}")

    print(f"\nTraining complete! Run dir: {results.save_dir}")


if __name__ == '__main__':
    main()
