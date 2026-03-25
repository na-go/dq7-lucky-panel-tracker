"""Windows Graphics Capture (WGC) - ウィンドウ単体キャプチャ

OBSのWindowキャプチャーと同じWindows Graphics Capture APIを使用。
Windows 10 バージョン 2004 (10.0.19041) 以降で利用可能。
DirectX描画のゲームウィンドウでも、上に別ウィンドウが重なっていても、
対象ウィンドウの内容だけをキャプチャできる。
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
from ctypes import (
    HRESULT,
    POINTER,
    WINFUNCTYPE,
    Structure,
    byref,
    c_int32,
    c_uint8,
    c_uint16,
    c_uint32,
    c_void_p,
    cast,
)
from typing import Optional

import cv2
import numpy as np


# ============================================================
# COM / D3D11 基盤
# ============================================================

class GUID(Structure):
    _fields_ = [
        ("Data1", c_uint32),
        ("Data2", c_uint16),
        ("Data3", c_uint16),
        ("Data4", c_uint8 * 8),
    ]


def _guid(s: str) -> GUID:
    h = s.replace("-", "")
    return GUID(
        int(h[0:8], 16), int(h[8:12], 16), int(h[12:16], 16),
        (c_uint8 * 8)(*bytes.fromhex(h[16:])),
    )


class SizeInt32(Structure):
    _fields_ = [("Width", c_int32), ("Height", c_int32)]


class D3D11_TEXTURE2D_DESC(Structure):
    _fields_ = [
        ("Width", c_uint32), ("Height", c_uint32),
        ("MipLevels", c_uint32), ("ArraySize", c_uint32),
        ("Format", c_uint32),
        ("SampleDesc_Count", c_uint32), ("SampleDesc_Quality", c_uint32),
        ("Usage", c_uint32), ("BindFlags", c_uint32),
        ("CPUAccessFlags", c_uint32), ("MiscFlags", c_uint32),
    ]


class D3D11_MAPPED_SUBRESOURCE(Structure):
    _fields_ = [
        ("pData", c_void_p),
        ("RowPitch", c_uint32),
        ("DepthPitch", c_uint32),
    ]


# 定数
DXGI_FORMAT_B8G8R8A8_UNORM = 87
D3D11_USAGE_STAGING = 3
D3D11_CPU_ACCESS_READ = 0x20000
D3D11_MAP_READ = 1

# GUIDs
IID_IDXGIDevice = _guid("54EC77FA-1377-44E6-8C32-88FD5F44C84C")
IID_IGraphicsCaptureItemInterop = _guid("3628E81B-3CAC-4C60-B7F4-23CE0E0C3356")
IID_IGraphicsCaptureItem = _guid("79C3F95B-31F7-4EC2-A464-632EF5D30760")
IID_IDirect3D11CaptureFramePoolStatics2 = _guid("589B103F-6BBC-5DF5-A991-02E28B3B66D5")
IID_IDirect3DDxgiInterfaceAccess = _guid("A9B3D012-3DF2-4EE3-B8D1-8695F457D3C1")
IID_ID3D11Texture2D = _guid("6F15AAF2-D208-4E89-9AB4-489535D34F9C")
IID_IGraphicsCaptureSession2 = _guid("2C39AE40-7D2E-5044-804E-8B6799D4CF9E")
IID_IGraphicsCaptureSession3 = _guid("7E2204C8-AAD6-5773-9F5E-E361AFB76E8C")


# ============================================================
# DLL / API 定義
# ============================================================

_d3d11 = ctypes.windll.d3d11
_combase = ctypes.windll.combase

# D3D11CreateDevice
_D3D11CreateDevice = _d3d11.D3D11CreateDevice
_D3D11CreateDevice.restype = HRESULT
_D3D11CreateDevice.argtypes = [
    c_void_p, c_uint32, c_void_p, c_uint32, c_void_p,
    c_uint32, c_uint32, POINTER(c_void_p), POINTER(c_uint32), POINTER(c_void_p),
]

# CreateDirect3D11DeviceFromDXGIDevice
_CreateDirect3D11DeviceFromDXGIDevice = _d3d11.CreateDirect3D11DeviceFromDXGIDevice
_CreateDirect3D11DeviceFromDXGIDevice.restype = HRESULT
_CreateDirect3D11DeviceFromDXGIDevice.argtypes = [c_void_p, POINTER(c_void_p)]

# WinRT 文字列
_WindowsCreateString = _combase.WindowsCreateString
_WindowsCreateString.restype = HRESULT
_WindowsCreateString.argtypes = [ctypes.c_wchar_p, c_uint32, POINTER(c_void_p)]

_WindowsDeleteString = _combase.WindowsDeleteString
_WindowsDeleteString.restype = HRESULT
_WindowsDeleteString.argtypes = [c_void_p]

# RoGetActivationFactory
_RoGetActivationFactory = _combase.RoGetActivationFactory
_RoGetActivationFactory.restype = HRESULT
_RoGetActivationFactory.argtypes = [c_void_p, POINTER(GUID), POINTER(c_void_p)]

# RoInitialize
_RoInitialize = _combase.RoInitialize
_RoInitialize.restype = HRESULT
_RoInitialize.argtypes = [c_uint32]


# ============================================================
# COM ヘルパー
# ============================================================

def _check_hr(hr: int, msg: str = ""):
    if hr < 0:
        raise OSError(f"COM error in {msg}: 0x{hr & 0xFFFFFFFF:08X}")


def _vtbl(ptr, index):
    """vtableのindex番目の関数ポインタを返す"""
    vtable = cast(cast(ptr, POINTER(c_void_p))[0], POINTER(c_void_p))
    return vtable[index]


def _release(ptr):
    """IUnknown::Release"""
    if ptr:
        f = cast(_vtbl(ptr, 2), WINFUNCTYPE(c_uint32, c_void_p))
        f(ptr)


def _qi(ptr, iid: GUID):
    """IUnknown::QueryInterface"""
    out = c_void_p()
    f = cast(_vtbl(ptr, 0), WINFUNCTYPE(HRESULT, c_void_p, POINTER(GUID), POINTER(c_void_p)))
    hr = f(ptr, byref(iid), byref(out))
    _check_hr(hr, "QueryInterface")
    return out


def _hstring(s: str):
    """HSTRING作成（呼び出し側でdeleteすること）"""
    h = c_void_p()
    _check_hr(_WindowsCreateString(s, len(s), byref(h)), "WindowsCreateString")
    return h


# ============================================================
# WgcCapture
# ============================================================

class WgcCapture:
    """Windows Graphics Capture ベースのウィンドウキャプチャ

    使い方:
        wgc = WgcCapture()
        if wgc.start(hwnd):
            frame = wgc.grab()  # BGR numpy array or None
        wgc.stop()
    """

    def __init__(self):
        self._d3d_device = None
        self._d3d_context = None
        self._winrt_device = None
        self._capture_item = None
        self._frame_pool = None
        self._session = None
        self._staging = None
        self._width = 0
        self._height = 0
        self._started = False
        self._last_frame: Optional[np.ndarray] = None

    def __del__(self):
        self.stop()

    # ------ public API ------

    def start(self, hwnd: int) -> bool:
        """指定ウィンドウのキャプチャを開始。成功でTrue。"""
        self.last_error: Optional[str] = None
        try:
            self._init_winrt()
            self._init_d3d11()
            self._create_capture_item(hwnd)
            self._read_item_size()
            self._create_frame_pool()
            self._start_session()
            self._create_staging()
            self._started = True
            return True
        except Exception as e:
            self.last_error = str(e)
            self.stop()
            return False

    @property
    def size(self) -> tuple[int, int]:
        return (self._width, self._height)

    def grab(self) -> Optional[np.ndarray]:
        """最新フレームをBGR numpy arrayで返す。

        新しいフレームがなければ直前のキャッシュを返す。
        ゲーム画面が静止している場合でも安定してフレームを返せる。
        """
        if not self._started:
            return None
        try:
            frame = self._get_frame()
            if frame is not None:
                self._last_frame = frame
                return frame
        except Exception:
            pass
        return self._last_frame

    def wait_first_frame(self, timeout: float = 1.0) -> bool:
        """最初のフレームが届くまで待機。タイムアウトでFalse。"""
        import time
        deadline = time.perf_counter() + timeout
        while time.perf_counter() < deadline:
            if self.grab() is not None:
                return True
            time.sleep(0.03)
        return False

    def stop(self):
        """全リソース解放"""
        self._started = False
        for name in ("_session", "_frame_pool", "_capture_item",
                     "_staging", "_winrt_device", "_d3d_context", "_d3d_device"):
            ptr = getattr(self, name, None)
            if ptr:
                _release(ptr)
                setattr(self, name, None)

    # ------ 初期化 ------

    def _init_winrt(self):
        hr = _RoInitialize(1)  # RO_INIT_MULTITHREADED
        # S_OK, S_FALSE (既に初期化済), RPC_E_CHANGED_MODE は許容
        if hr < 0 and (hr & 0xFFFFFFFF) != 0x80010106:
            _check_hr(hr, "RoInitialize")

    def _init_d3d11(self):
        dev, ctx, fl = c_void_p(), c_void_p(), c_uint32()
        _check_hr(
            _D3D11CreateDevice(None, 1, None, 0x20, None, 0, 7,
                               byref(dev), byref(fl), byref(ctx)),
            "D3D11CreateDevice",
        )
        self._d3d_device = dev.value
        self._d3d_context = ctx.value

        # IDXGIDevice → WinRT IDirect3DDevice
        dxgi = _qi(self._d3d_device, IID_IDXGIDevice)
        try:
            winrt_dev = c_void_p()
            _check_hr(
                _CreateDirect3D11DeviceFromDXGIDevice(dxgi.value, byref(winrt_dev)),
                "CreateDirect3D11DeviceFromDXGIDevice",
            )
            self._winrt_device = winrt_dev.value
        finally:
            _release(dxgi.value)

    def _create_capture_item(self, hwnd: int):
        hs = _hstring("Windows.Graphics.Capture.GraphicsCaptureItem")
        try:
            factory = c_void_p()
            _check_hr(
                _RoGetActivationFactory(hs, byref(IID_IGraphicsCaptureItemInterop), byref(factory)),
                "ActivationFactory(CaptureItem)",
            )
            try:
                # IGraphicsCaptureItemInterop::CreateForWindow [vtable 3]
                item = c_void_p()
                f = cast(_vtbl(factory.value, 3),
                         WINFUNCTYPE(HRESULT, c_void_p, wintypes.HWND,
                                     POINTER(GUID), POINTER(c_void_p)))
                _check_hr(
                    f(factory.value, hwnd, byref(IID_IGraphicsCaptureItem), byref(item)),
                    "CreateForWindow",
                )
                self._capture_item = item.value
            finally:
                _release(factory.value)
        finally:
            _WindowsDeleteString(hs)

    def _read_item_size(self):
        # IGraphicsCaptureItem::get_Size [vtable 7]
        sz = SizeInt32()
        f = cast(_vtbl(self._capture_item, 7),
                 WINFUNCTYPE(HRESULT, c_void_p, POINTER(SizeInt32)))
        _check_hr(f(self._capture_item, byref(sz)), "get_Size")
        self._width, self._height = sz.Width, sz.Height

    def _create_frame_pool(self):
        hs = _hstring("Windows.Graphics.Capture.Direct3D11CaptureFramePool")
        try:
            factory = c_void_p()
            _check_hr(
                _RoGetActivationFactory(hs, byref(IID_IDirect3D11CaptureFramePoolStatics2), byref(factory)),
                "ActivationFactory(FramePool)",
            )
            try:
                # IDirect3D11CaptureFramePoolStatics2::CreateFreeThreaded [vtable 6]
                pool = c_void_p()
                sz = SizeInt32(self._width, self._height)
                f = cast(_vtbl(factory.value, 6),
                         WINFUNCTYPE(HRESULT, c_void_p,
                                     c_void_p, c_int32, c_int32, SizeInt32,
                                     POINTER(c_void_p)))
                _check_hr(
                    f(factory.value, self._winrt_device,
                      DXGI_FORMAT_B8G8R8A8_UNORM, 2, sz, byref(pool)),
                    "CreateFreeThreaded",
                )
                self._frame_pool = pool.value
            finally:
                _release(factory.value)
        finally:
            _WindowsDeleteString(hs)

    def _start_session(self):
        # IDirect3D11CaptureFramePool::CreateCaptureSession [vtable 10]
        sess = c_void_p()
        f = cast(_vtbl(self._frame_pool, 10),
                 WINFUNCTYPE(HRESULT, c_void_p, c_void_p, POINTER(c_void_p)))
        _check_hr(f(self._frame_pool, self._capture_item, byref(sess)),
                  "CreateCaptureSession")
        self._session = sess.value

        # Win11: キャプチャ枠線を非表示
        try:
            s3 = _qi(self._session, IID_IGraphicsCaptureSession3)
            # put_IsBorderRequired [vtable 7]
            f = cast(_vtbl(s3.value, 7), WINFUNCTYPE(HRESULT, c_void_p, c_int32))
            f(s3.value, 0)
            _release(s3.value)
        except Exception:
            pass

        # カーソル非表示
        try:
            s2 = _qi(self._session, IID_IGraphicsCaptureSession2)
            # put_IsCursorCaptureEnabled [vtable 7]
            f = cast(_vtbl(s2.value, 7), WINFUNCTYPE(HRESULT, c_void_p, c_int32))
            f(s2.value, 0)
            _release(s2.value)
        except Exception:
            pass

        # IGraphicsCaptureSession::StartCapture [vtable 6]
        f = cast(_vtbl(self._session, 6), WINFUNCTYPE(HRESULT, c_void_p))
        _check_hr(f(self._session), "StartCapture")

    def _create_staging(self):
        desc = D3D11_TEXTURE2D_DESC(
            Width=self._width, Height=self._height,
            MipLevels=1, ArraySize=1,
            Format=DXGI_FORMAT_B8G8R8A8_UNORM,
            SampleDesc_Count=1, SampleDesc_Quality=0,
            Usage=D3D11_USAGE_STAGING, BindFlags=0,
            CPUAccessFlags=D3D11_CPU_ACCESS_READ, MiscFlags=0,
        )
        tex = c_void_p()
        # ID3D11Device::CreateTexture2D [vtable 5]
        f = cast(_vtbl(self._d3d_device, 5),
                 WINFUNCTYPE(HRESULT, c_void_p,
                             POINTER(D3D11_TEXTURE2D_DESC), c_void_p, POINTER(c_void_p)))
        _check_hr(f(self._d3d_device, byref(desc), None, byref(tex)),
                  "CreateTexture2D(staging)")
        self._staging = tex.value

    # ------ フレーム取得 ------

    def _get_frame(self) -> Optional[np.ndarray]:
        # IDirect3D11CaptureFramePool::TryGetNextFrame [vtable 7]
        frame = c_void_p()
        f = cast(_vtbl(self._frame_pool, 7),
                 WINFUNCTYPE(HRESULT, c_void_p, POINTER(c_void_p)))
        hr = f(self._frame_pool, byref(frame))
        if hr < 0 or not frame.value:
            return None

        try:
            return self._copy_frame(frame.value)
        finally:
            _release(frame.value)

    def _copy_frame(self, frame_ptr) -> np.ndarray:
        # get_Surface [vtable 6]
        surface = c_void_p()
        f = cast(_vtbl(frame_ptr, 6),
                 WINFUNCTYPE(HRESULT, c_void_p, POINTER(c_void_p)))
        _check_hr(f(frame_ptr, byref(surface)), "get_Surface")

        try:
            # IDirect3DDxgiInterfaceAccess::GetInterface [vtable 3] → ID3D11Texture2D
            access = _qi(surface.value, IID_IDirect3DDxgiInterfaceAccess)
            try:
                tex = c_void_p()
                f = cast(_vtbl(access.value, 3),
                         WINFUNCTYPE(HRESULT, c_void_p, POINTER(GUID), POINTER(c_void_p)))
                _check_hr(f(access.value, byref(IID_ID3D11Texture2D), byref(tex)),
                          "GetInterface(Texture2D)")
                try:
                    return self._texture_to_numpy(tex.value)
                finally:
                    _release(tex.value)
            finally:
                _release(access.value)
        finally:
            _release(surface.value)

    def _texture_to_numpy(self, tex) -> np.ndarray:
        # テクスチャサイズ取得
        desc = D3D11_TEXTURE2D_DESC()
        f = cast(_vtbl(tex, 10),
                 WINFUNCTYPE(None, c_void_p, POINTER(D3D11_TEXTURE2D_DESC)))
        f(tex, byref(desc))
        w, h = desc.Width, desc.Height

        # ステージングにコピー
        # ID3D11DeviceContext::CopyResource [vtable 47]
        f = cast(_vtbl(self._d3d_context, 47),
                 WINFUNCTYPE(None, c_void_p, c_void_p, c_void_p))
        f(self._d3d_context, self._staging, tex)

        # Map [vtable 14]
        mapped = D3D11_MAPPED_SUBRESOURCE()
        f = cast(_vtbl(self._d3d_context, 14),
                 WINFUNCTYPE(HRESULT, c_void_p, c_void_p, c_uint32,
                             c_uint32, c_uint32, POINTER(D3D11_MAPPED_SUBRESOURCE)))
        _check_hr(f(self._d3d_context, self._staging, 0, D3D11_MAP_READ, 0, byref(mapped)),
                  "Map")

        try:
            pitch = mapped.RowPitch
            src = (c_uint8 * (pitch * h)).from_address(mapped.pData)
            buf = bytes(src)

            if pitch == w * 4:
                frame = np.frombuffer(buf, dtype=np.uint8).reshape(h, w, 4)
            else:
                # RowPitchにパディングがある場合
                frame = np.zeros((h, w, 4), dtype=np.uint8)
                for y in range(h):
                    start = y * pitch
                    frame[y] = np.frombuffer(
                        buf[start:start + w * 4], dtype=np.uint8,
                    ).reshape(w, 4)

            return cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
        finally:
            # Unmap [vtable 15]
            f = cast(_vtbl(self._d3d_context, 15),
                     WINFUNCTYPE(None, c_void_p, c_void_p, c_uint32))
            f(self._d3d_context, self._staging, 0)


# ============================================================
# ユーティリティ
# ============================================================

def is_available() -> bool:
    """WGCが利用可能か（Windows 10 2004+）"""
    try:
        hs = _hstring("Windows.Graphics.Capture.Direct3D11CaptureFramePool")
        factory = c_void_p()
        hr = _RoInitialize(1)
        hr = _RoGetActivationFactory(hs, byref(IID_IDirect3D11CaptureFramePoolStatics2), byref(factory))
        _WindowsDeleteString(hs)
        if hr >= 0 and factory.value:
            _release(factory.value)
            return True
        return False
    except Exception:
        return False
