import xarray as xr
import matplotlib.pyplot as plt
import cartopy.crs as ccrs

# Open anomaly dataset (NetCDF example)
ds = xr.open_dataset("temperature_anomaly.nc")
anomaly = ds["t2m_anomaly"].sel(time="2025-08")

# Define diverging colormap
from matplotlib.colors import ListedColormap

colors = ["darkblue", "blue", "lightblue", "white", "lightcoral", "red", "darkred"]
cmap = ListedColormap(colors)

# Plot
plt.figure(figsize=(10,6))
ax = plt.axes(projection=ccrs.PlateCarree())
anomaly.plot(
    ax=ax,
    transform=ccrs.PlateCarree(),
    cmap=cmap,
    vmin=-3, vmax=3,  # anomaly scale range
    cbar_kwargs={"label": "Temperature Anomaly (°C)"}
)
ax.coastlines()
ax.set_title("Temperature Anomaly Map", fontsize=14)
plt.show()
