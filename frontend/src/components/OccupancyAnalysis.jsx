import { useState, useEffect } from 'react';
import {
    LineChart,
    Line,
    BarChart,
    Bar,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer,
    Legend,
} from 'recharts';
import { API_BASE } from '../api';

export default function OccupancyAnalysis() {
    const [allData, setAllData] = useState(null);
    const [data, setData] = useState(null);
    const [cameraList, setCameraList] = useState([]);
    const [selectedCamera, setSelectedCamera] = useState('');
    const [loading, setLoading] = useState(true);
    const [filterLoading, setFilterLoading] = useState(false);
    const [error, setError] = useState(null);

    // Initial load: fetch all occupancy data and build camera list
    useEffect(() => {
        let cancelled = false;
        setLoading(true);
        setError(null);
        const url = `${API_BASE}/api/occupancy?limit=2000`;
        fetch(url)
            .then((res) => {
                const ct = res.headers.get('content-type') || '';
                if (!ct.includes('application/json')) {
                    throw new Error('Backend returned non-JSON. Is the API server running? Set VITE_API_URL in .env if the backend is on a different port.');
                }
                return res.json();
            })
            .then((json) => {
                if (cancelled) return;
                if (json.success) {
                    const payload = {
                        by_date: json.by_date || [],
                        by_camera: json.by_camera || [],
                        raw_count: (json.data || []).length,
                    };
                    setAllData(payload);
                    setData(payload);
                    const cameras = (json.by_camera || []).map((b) => b.camera_number).filter(Boolean);
                    setCameraList([...new Set(cameras)].sort());
                } else {
                    setError(json.error || 'Failed to load occupancy data');
                    setAllData(null);
                    setData(null);
                    setCameraList([]);
                }
            })
            .catch((err) => {
                if (!cancelled) {
                    setError(err.message || 'Network error');
                    setAllData(null);
                    setData(null);
                    setCameraList([]);
                }
            })
            .finally(() => {
                if (!cancelled) setLoading(false);
            });
        return () => { cancelled = true; };
    }, []);

    // When camera dropdown changes: show All or refetch for that camera
    useEffect(() => {
        if (loading || !allData) return;
        if (selectedCamera === '') {
            setData(allData);
            return;
        }
        let cancelled = false;
        setFilterLoading(true);
        const url = `${API_BASE}/api/occupancy?limit=2000&camera_number=${encodeURIComponent(selectedCamera)}`;
        fetch(url)
            .then((res) => res.json())
            .then((json) => {
                if (cancelled) return;
                if (json.success) {
                    setData({
                        by_date: json.by_date || [],
                        by_camera: json.by_camera || [],
                        raw_count: (json.data || []).length,
                    });
                }
            })
            .catch(() => {
                if (!cancelled) setData(allData);
            })
            .finally(() => {
                if (!cancelled) setFilterLoading(false);
            });
        return () => { cancelled = true; };
    }, [selectedCamera, loading, allData]);

    const chartPrimary = '#4ade80';
    const chartSecondary = 'rgba(74, 222, 128, 0.55)';
    const gridColor = 'rgba(255,255,255,0.1)';
    const axisColor = 'rgba(255,255,255,0.7)';
    const tooltipBg = 'rgba(30, 41, 59, 0.97)';
    const tooltipBorder = 'rgba(255,255,255,0.15)';

    if (loading) {
        return (
            <div className="occupancy-analysis">
                <div className="occupancy-analysis-header">Occupancy Analysis</div>
                <p className="placeholder-text">Loading occupancy data from database…</p>
            </div>
        );
    }

    if (error) {
        return (
            <div className="occupancy-analysis">
                <div className="occupancy-analysis-header">Occupancy Analysis</div>
                <p className="placeholder-text" style={{ color: 'rgba(239, 68, 68, 0.9)' }}>
                    {error}
                </p>
            </div>
        );
    }

    const byDate = data?.by_date || [];
    const byCamera = data?.by_camera || [];
    const hasAny = byDate.length > 0 || byCamera.length > 0;

    if (!hasAny) {
        return (
            <div className="occupancy-analysis">
                <div className="occupancy-analysis-header">Occupancy Analysis</div>
                <p className="placeholder-text">
                    No occupancy data in the database yet. Process video with occupancy logging enabled to see graphs here.
                </p>
            </div>
        );
    }

    const CustomLineTooltip = ({ active, payload, label }) => {
        if (!active || !payload?.length) return null;
        return (
            <div className="occupancy-tooltip">
                <div className="occupancy-tooltip-label">{label}</div>
                {payload.map((p) => (
                    <div key={p.dataKey} className="occupancy-tooltip-row">
                        <span className="occupancy-tooltip-dot" style={{ background: p.color }} />
                        <span>{p.name}:</span>
                        <strong>{Number(p.value)} people</strong>
                    </div>
                ))}
            </div>
        );
    };

    const CustomBarTooltip = ({ active, payload, label }) => {
        if (!active || !payload?.length) return null;
        return (
            <div className="occupancy-tooltip">
                <div className="occupancy-tooltip-label">Camera: {label}</div>
                {payload.map((p) => (
                    <div key={p.dataKey} className="occupancy-tooltip-row">
                        <span className="occupancy-tooltip-dot" style={{ background: p.color }} />
                        <span>{p.name}:</span>
                        <strong>{Number(p.value)} people</strong>
                    </div>
                ))}
            </div>
        );
    };

    return (
        <div className="occupancy-analysis">
            <div className="occupancy-analysis-top">
                <h3 className="occupancy-analysis-title">Occupancy Analysis</h3>
                <div className="occupancy-analysis-controls">
                    <label htmlFor="occupancy-camera-select" className="occupancy-camera-label">Camera</label>
                    <select
                        id="occupancy-camera-select"
                        className="occupancy-camera-select"
                        value={selectedCamera}
                        onChange={(e) => setSelectedCamera(e.target.value)}
                        disabled={filterLoading}
                    >
                        <option value="">All cameras</option>
                        {cameraList.map((cam) => (
                            <option key={cam} value={cam}>{cam}</option>
                        ))}
                    </select>
                    {filterLoading && <span className="occupancy-filter-loading">Loading…</span>}
                </div>
                <span className="occupancy-analysis-badge">{data.raw_count.toLocaleString()} records</span>
            </div>

            {byDate.length > 0 && (
                <div className="occupancy-chart-card">
                    <h4 className="occupancy-chart-title">Occupancy over time (by date)</h4>
                    <p className="occupancy-chart-subtitle">Max and average people count per day</p>
                    <ResponsiveContainer width="100%" height={240}>
                        <LineChart
                            data={byDate}
                            margin={{ top: 16, right: 16, left: 8, bottom: 24 }}
                        >
                            <CartesianGrid strokeDasharray="3 3" stroke={gridColor} vertical={false} />
                            <XAxis
                                dataKey="date"
                                tick={{ fontSize: 11, fill: axisColor, fontFamily: 'inherit' }}
                                axisLine={{ stroke: gridColor }}
                                tickLine={{ stroke: gridColor }}
                                label={{ value: 'Date', position: 'insideBottom', offset: -8, fill: axisColor, fontSize: 11 }}
                            />
                            <YAxis
                                tick={{ fontSize: 11, fill: axisColor, fontFamily: 'inherit' }}
                                axisLine={{ stroke: gridColor }}
                                tickLine={{ stroke: gridColor }}
                                allowDecimals={false}
                                domain={[0, 'auto']}
                                label={{ value: 'People', angle: -90, position: 'insideLeft', fill: axisColor, fontSize: 11 }}
                            />
                            <Tooltip content={<CustomLineTooltip />} />
                            <Legend wrapperStyle={{ fontSize: 11 }} iconType="line" iconSize={10} />
                            <Line
                                type="monotone"
                                dataKey="max_people"
                                name="Max people"
                                stroke={chartPrimary}
                                strokeWidth={2.5}
                                dot={{ fill: chartPrimary, r: 4, strokeWidth: 0 }}
                                activeDot={{ r: 5, stroke: chartPrimary, strokeWidth: 2 }}
                            />
                            <Line
                                type="monotone"
                                dataKey="avg_people"
                                name="Avg people"
                                stroke={chartSecondary}
                                strokeWidth={2}
                                strokeDasharray="5 5"
                                dot={{ fill: chartSecondary, r: 3, strokeWidth: 0 }}
                                activeDot={{ r: 4 }}
                            />
                        </LineChart>
                    </ResponsiveContainer>
                </div>
            )}

            {byCamera.length > 0 && (
                <div className="occupancy-chart-card">
                    <h4 className="occupancy-chart-title">Occupancy by camera</h4>
                    <p className="occupancy-chart-subtitle">Max and average people per camera</p>
                    <ResponsiveContainer width="100%" height={Math.max(200, byCamera.length * 44)}>
                        <BarChart
                            data={byCamera}
                            margin={{ top: 16, right: 16, left: 8, bottom: 24 }}
                            layout="vertical"
                            barCategoryGap={12}
                            barGap={6}
                        >
                            <CartesianGrid strokeDasharray="3 3" stroke={gridColor} horizontal={true} vertical={false} />
                            <XAxis
                                type="number"
                                tick={{ fontSize: 11, fill: axisColor, fontFamily: 'inherit' }}
                                axisLine={{ stroke: gridColor }}
                                tickLine={{ stroke: gridColor }}
                                allowDecimals={false}
                                domain={[0, 'auto']}
                                label={{ value: 'People', position: 'insideBottom', offset: -8, fill: axisColor, fontSize: 11 }}
                            />
                            <YAxis
                                type="category"
                                dataKey="camera_number"
                                width={72}
                                tick={{ fontSize: 11, fill: axisColor, fontFamily: 'inherit' }}
                                axisLine={{ stroke: gridColor }}
                                tickLine={false}
                            />
                            <Tooltip content={<CustomBarTooltip />} />
                            <Legend wrapperStyle={{ fontSize: 11 }} iconType="square" iconSize={10} />
                            <Bar dataKey="max_people" name="Max people" fill={chartPrimary} radius={[0, 4, 4, 0]} />
                            <Bar dataKey="avg_people" name="Avg people" fill={chartSecondary} radius={[0, 4, 4, 0]} />
                        </BarChart>
                    </ResponsiveContainer>
                </div>
            )}
        </div>
    );
}
