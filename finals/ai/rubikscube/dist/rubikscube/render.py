from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from math import ceil, cos, radians, sin
from pathlib import Path
from typing import Iterable, Literal, Sequence, cast

from .core import AXIS_INDEX, FACE_COLORS, MOVE_SPECS, CubeState, apply_move, canonicalize_move, is_solved_state
from .observations import FaceGrid, FullCubeObservation, SolvedFacesObservation, observe_full_cube, observe_solved_faces

Point3D = tuple[float, float, float]
RenderMode = Literal["normal", "solved-mask"]

_FACE_FRAME = {
    "F": ((0.0, 0.0, 1.02), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
    "B": ((0.0, 0.0, -1.02), (-1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
    "U": ((0.0, 1.02, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, -1.0)),
    "D": ((0.0, -1.02, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    "R": ((1.02, 0.0, 0.0), (0.0, 0.0, -1.0), (0.0, 1.0, 0.0)),
    "L": ((-1.02, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 1.0, 0.0)),
}
_FACE_ORDER = ("U", "D", "F", "B", "L", "R")
_HIDDEN_STICKER_COLOR = "#808080"
_HIDDEN_FACE_GRID = cast(
    FaceGrid,
    ((_HIDDEN_STICKER_COLOR, _HIDDEN_STICKER_COLOR), (_HIDDEN_STICKER_COLOR, _HIDDEN_STICKER_COLOR)),
)
_STICKER_INSET = 0.015
_STICKER_EDGE_WIDTH = 4.6
_PREFERRED_INTERACTIVE_BACKEND = "QtAgg"
_NON_INTERACTIVE_BACKENDS = {
    "agg",
    "cairo",
    "pdf",
    "pgf",
    "ps",
    "svg",
    "template",
    "module://matplotlibinline.backendinline",
}


@dataclass(slots=True)
class _ViewState:
    elev: float = 25
    azim: float = 135
    roll: float = 0

    def capture(self, ax: object) -> None:
        self.elev = getattr(ax, "elev", self.elev)
        self.azim = getattr(ax, "azim", self.azim)
        self.roll = getattr(ax, "roll", self.roll)

    def restore(self, ax: object) -> None:
        _set_view(ax, elev=self.elev, azim=self.azim, roll=self.roll)


@dataclass(frozen=True, slots=True)
class StickerPolygon:
    face: str
    row: int
    col: int
    color: str
    vertices: tuple[Point3D, Point3D, Point3D, Point3D]


class RendererUnavailable(RuntimeError):
    pass


class RecordingUnavailable(RuntimeError):
    pass


def is_matplotlib_available() -> bool:
    try:
        import matplotlib  # noqa: F401
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # noqa: F401
    except ImportError:
        return False
    return True


def supports_interactive_rendering() -> bool:
    return _ensure_interactive_backend()


def selected_backend() -> str:
    if not is_matplotlib_available():
        return "unavailable"
    return _current_backend()


def _ensure_interactive_backend() -> bool:
    if not is_matplotlib_available():
        return False

    import matplotlib

    if _backend_is_interactive(_current_backend()):
        return True
    if os.environ.get("MPLBACKEND") or _pyplot_is_imported():
        return False
    try:
        matplotlib.use(_PREFERRED_INTERACTIVE_BACKEND, force=False)
    except (ImportError, ValueError, RuntimeError):
        return _backend_is_interactive(_current_backend())
    return _backend_is_interactive(_current_backend())


def _current_backend() -> str:
    import matplotlib

    return str(matplotlib.get_backend())


def _backend_is_interactive(backend: object) -> bool:
    return _normalize_backend_name(backend) not in _NON_INTERACTIVE_BACKENDS


def _normalize_backend_name(backend: object) -> str:
    return str(backend or "").lower().replace("-", "").replace("_", "")


def _pyplot_is_imported() -> bool:
    return "matplotlib.pyplot" in sys.modules


def can_record_mp4() -> bool:
    if not is_matplotlib_available():
        return False
    from matplotlib import animation

    return animation.writers.is_available("ffmpeg")


def build_sticker_polygons(observation: FullCubeObservation, inset: float = _STICKER_INSET) -> tuple[StickerPolygon, ...]:
    stickers: list[StickerPolygon] = []
    for face in _FACE_ORDER:
        face_origin, right, up = _FACE_FRAME[face]
        for row in range(2):
            for col in range(2):
                u_min, u_max = _cell_bounds(col, inset)
                v_min, v_max = _cell_bounds(1 - row, inset)
                vertices = (
                    _point_on_face(face_origin, right, up, u_min, v_min),
                    _point_on_face(face_origin, right, up, u_max, v_min),
                    _point_on_face(face_origin, right, up, u_max, v_max),
                    _point_on_face(face_origin, right, up, u_min, v_max),
                )
                stickers.append(
                    StickerPolygon(
                        face=face,
                        row=row,
                        col=col,
                        color=observation[face][row][col],
                        vertices=vertices,
                    )
                )
    return tuple(stickers)


def build_sticker_polygons_for_state(
    state: CubeState,
    *,
    render_mode: RenderMode = "normal",
    inset: float = _STICKER_INSET,
) -> tuple[StickerPolygon, ...]:
    return build_sticker_polygons(observation_for_render_mode(state, render_mode), inset=inset)


class CubeRenderer:
    def __init__(self, *, render_mode: RenderMode = "normal", debug: bool = False) -> None:
        if not is_matplotlib_available():
            raise RendererUnavailable("Matplotlib is not installed.")

        import matplotlib.pyplot as plt

        self._plt = plt
        self.render_mode = render_mode
        self.debug = debug
        self._debug_frame_index = 0
        self._view_state = _ViewState()
        self.figure = plt.figure(figsize=(6, 6))
        self.ax = self.figure.add_subplot(111, projection="3d")
        self._configure_axes(reset_view=True)
        self._view_state.capture(self.ax)
        self.figure.canvas.mpl_connect("button_release_event", self._refresh_saved_view)

    def draw_state(self, state: CubeState, *, render_mode: RenderMode | None = None) -> bool:
        return self.draw_snapshot(observation_for_render_mode(state, render_mode or self.render_mode))

    def draw_snapshot(self, observation: FullCubeObservation) -> bool:
        stickers = build_sticker_polygons(observation)
        self._render_polygons(stickers, label="draw_snapshot")
        self._plt.pause(0.001)
        return True

    def animate_move(
        self,
        before_state: CubeState,
        move: str,
        after_state: CubeState,
        *,
        move_duration: float = 0.05,
        render_mode: RenderMode | None = None,
    ) -> bool:
        token = canonicalize_move(move)
        active_mode = render_mode or self.render_mode
        frame_count = _frame_count_for_duration(move_duration)
        interval_seconds = move_duration / frame_count

        for polygons in _animated_move_frames(
            before_state,
            move,
            after_state,
            render_mode=active_mode,
            frame_count=frame_count,
        ):
            self._render_polygons(polygons, label=f"move={token}")
            self._plt.pause(interval_seconds)

        self.draw_state(after_state, render_mode=active_mode)
        return True

    def record_mp4(
        self,
        initial_state: CubeState,
        moves: Sequence[str],
        output_path: str,
        *,
        move_duration: float = 0.05,
        render_mode: RenderMode | None = None,
        fps: int = 12,
        dpi: int = 100,
    ) -> Path:
        if not can_record_mp4():
            raise RecordingUnavailable("MP4 export requires ffmpeg to be installed and visible to Matplotlib.")

        from matplotlib import animation

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        active_mode = render_mode or self.render_mode
        writer = animation.FFMpegWriter(fps=fps, bitrate=1200, extra_args=["-pix_fmt", "yuv420p"])

        with writer.saving(self.figure, str(path), dpi=dpi):
            current_state = initial_state
            if not (active_mode == "solved-mask" and moves and is_solved_state(current_state)):
                self.draw_state(current_state, render_mode=active_mode)
                writer.grab_frame()
            for move in moves:
                next_state = apply_move(current_state, move)
                for polygons in _animated_move_frames(
                    current_state,
                    move,
                    next_state,
                    render_mode=active_mode,
                    frame_count=_frame_count_for_duration(move_duration, fps=fps),
                ):
                    self._render_polygons(polygons, label=f"record move={move}")
                    writer.grab_frame()
                current_state = next_state
            self.draw_state(current_state, render_mode=active_mode)
            writer.grab_frame()

        return path

    def show(self, *, block: bool = True) -> None:
        self._plt.show(block=block)

    def _configure_axes(self, *, reset_view: bool = False) -> None:
        self.ax.set_xlim((-1.4, 1.4))
        self.ax.set_ylim((-1.4, 1.4))
        self.ax.set_zlim((-1.4, 1.4))
        self.ax.set_box_aspect((1, 1, 1))
        if reset_view:
            self._view_state.restore(self.ax)
        self.ax.set_axis_off()

    def _refresh_saved_view(self, _event: object | None = None) -> None:
        self._view_state.capture(self.ax)

    def _draw_polygons(self, stickers: Iterable[StickerPolygon]) -> None:
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection

        self._refresh_saved_view()
        self.ax.cla()
        self._configure_axes()
        self._view_state.restore(self.ax)

        sticker_list = tuple(stickers)
        for polygon, facecolor in ((sticker.vertices, sticker.color) for sticker in sticker_list):
            collection = Poly3DCollection(
                [tuple(_display_point(vertex) for vertex in polygon)],
                facecolors=[facecolor],
                edgecolors="black",
                linewidths=_STICKER_EDGE_WIDTH,
                zsort="average",
            )
            self.ax.add_collection3d(collection)

    def _render_polygons(self, stickers: Iterable[StickerPolygon], *, label: str = "frame") -> None:
        sticker_list = tuple(stickers)
        if self.debug:
            self._debug_print_tiles(sticker_list, label=label)
        self._draw_polygons(sticker_list)
        self.figure.canvas.draw()

    def _debug_print_tiles(self, stickers: Sequence[StickerPolygon], *, label: str) -> None:
        print(
            f"[render-debug] frame={self._debug_frame_index} mode={self.render_mode} label={label}",
            file=sys.stderr,
        )
        for sticker in stickers:
            print(
                f"[render-debug] {sticker.face}[{sticker.row},{sticker.col}]={sticker.color}",
                file=sys.stderr,
            )
        self._debug_frame_index += 1


def draw_state(state: CubeState, *, render_mode: RenderMode = "normal", debug: bool = False) -> bool:
    if not is_matplotlib_available():
        return False
    renderer = CubeRenderer(render_mode=render_mode, debug=debug)
    return renderer.draw_state(state, render_mode=render_mode)


def animate_move(
    before_state: CubeState,
    move: str,
    after_state: CubeState,
    *,
    move_duration: float = 0.05,
    render_mode: RenderMode = "normal",
    debug: bool = False,
) -> bool:
    if not is_matplotlib_available() or not supports_interactive_rendering():
        return False
    renderer = CubeRenderer(render_mode=render_mode, debug=debug)
    renderer.draw_state(before_state, render_mode=render_mode)
    return renderer.animate_move(before_state, move, after_state, move_duration=move_duration, render_mode=render_mode)


def record_mp4(
    initial_state: CubeState,
    moves: Sequence[str],
    output_path: str,
    *,
    move_duration: float = 0.05,
    render_mode: RenderMode = "normal",
    fps: int = 12,
    dpi: int = 100,
    debug: bool = False,
) -> Path:
    if not is_matplotlib_available():
        raise RecordingUnavailable("Matplotlib is not installed.")
    renderer = CubeRenderer(render_mode=render_mode, debug=debug)
    return renderer.record_mp4(
        initial_state,
        moves,
        output_path,
        move_duration=move_duration,
        render_mode=render_mode,
        fps=fps,
        dpi=dpi,
    )


def observation_for_render_mode(state: CubeState, render_mode: RenderMode) -> FullCubeObservation:
    if render_mode == "normal":
        return observe_full_cube(state)
    if render_mode == "solved-mask":
        return _masked_observation(observe_full_cube(state), observe_solved_faces(state))
    raise ValueError(f"Unsupported render mode: {render_mode}")


def _cell_bounds(index: int, inset: float) -> tuple[float, float]:
    start = -1.0 + index
    end = start + 1.0
    return start + inset, end - inset


def _point_on_face(origin: Point3D, right: Point3D, up: Point3D, u: float, v: float) -> Point3D:
    return (
        origin[0] + right[0] * u + up[0] * v,
        origin[1] + right[1] * u + up[1] * v,
        origin[2] + right[2] * u + up[2] * v,
    )


def _display_point(point: Point3D) -> Point3D:
    x, y, z = point
    return (-x, z, y)


def _set_view(ax: object, *, elev: float, azim: float, roll: float) -> None:
    try:
        ax.view_init(elev=elev, azim=azim, roll=roll)  # type: ignore[attr-defined]
    except TypeError:
        ax.view_init(elev=elev, azim=azim)  # type: ignore[attr-defined]



def _rotation_spec(move: str) -> tuple[str, int, int]:
    axis_name, layer_sign, base_rotation = MOVE_SPECS[move[0]]
    rotation = -base_rotation if move.endswith("'") else base_rotation
    return axis_name, layer_sign, rotation


def _animated_move_frames(
    before_state: CubeState,
    move: str,
    after_state: CubeState,
    *,
    render_mode: RenderMode,
    frame_count: int,
) -> tuple[tuple[StickerPolygon, ...], ...]:
    token = canonicalize_move(move)
    before_stickers = build_sticker_polygons(observation_for_render_mode(before_state, render_mode))
    axis_name, layer_sign, rotation = _rotation_spec(token)
    affected = {
        index
        for index, sticker in enumerate(before_stickers)
        if _sticker_center(sticker.vertices)[AXIS_INDEX[axis_name]] * layer_sign > 0.2
    }
    frames: list[tuple[StickerPolygon, ...]] = []
    for frame_index in range(frame_count):
        angle = rotation * 90.0 * frame_index / (frame_count - 1)
        animated: list[StickerPolygon] = []
        for index, sticker in enumerate(before_stickers):
            vertices = sticker.vertices
            if index in affected:
                vertices = tuple(_rotate_point(vertex, axis_name, angle) for vertex in vertices)
            animated.append(
                StickerPolygon(
                    face=sticker.face,
                    row=sticker.row,
                    col=sticker.col,
                    color=sticker.color,
                    vertices=vertices,
                )
            )
        frames.append(tuple(animated))
    return tuple(frames)


def _frame_count_for_duration(move_duration: float, *, fps: int = 12) -> int:
    if move_duration <= 0:
        raise ValueError("move_duration must be positive.")
    return max(2, ceil(move_duration * fps))


def _masked_observation(
    full_observation: FullCubeObservation,
    solved_faces: SolvedFacesObservation,
) -> FullCubeObservation:
    masked: FullCubeObservation = {}
    for face in _FACE_ORDER:
        face_color = FACE_COLORS[face]
        if solved_faces[face_color]:
            masked[face] = full_observation[face]
            continue
        masked[face] = _HIDDEN_FACE_GRID
    return masked


def _sticker_center(vertices: tuple[Point3D, Point3D, Point3D, Point3D]) -> Point3D:
    count = len(vertices)
    return (
        sum(point[0] for point in vertices) / count,
        sum(point[1] for point in vertices) / count,
        sum(point[2] for point in vertices) / count,
    )


def _rotate_point(point: Point3D, axis_name: str, degrees: float) -> Point3D:
    angle = radians(degrees)
    x, y, z = point
    if axis_name == "x":
        return (x, y * cos(angle) - z * sin(angle), y * sin(angle) + z * cos(angle))
    if axis_name == "y":
        return (x * cos(angle) + z * sin(angle), y, -x * sin(angle) + z * cos(angle))
    if axis_name == "z":
        return (x * cos(angle) - y * sin(angle), x * sin(angle) + y * cos(angle), z)
    raise ValueError(f"Unsupported axis: {axis_name}")
