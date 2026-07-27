"""
Curated city table for the public SEO panchangam pages
(/panchangam/{lang}/{city}/{date}) and the sitemap.

Slugs are URL-safe, stable identifiers — never rename one once published, or
its indexed pages 404. Coordinates are city-centre approximations (panchangam
values change slowly with location). Timezone is resolved by the engine from
the coordinates (astro_engine.get_timezone_offset), so no tz field is stored;
for the handful of diaspora cities that estimate is DST-unaware, which is
acceptable for a daily panchangam page.
"""

# slug -> (display name, latitude, longitude)
CITIES = {
    # Tamil Nadu
    "chennai": ("Chennai", 13.0827, 80.2707),
    "coimbatore": ("Coimbatore", 11.0168, 76.9558),
    "madurai": ("Madurai", 9.9252, 78.1198),
    "tiruchirappalli": ("Tiruchirappalli", 10.7905, 78.7047),
    "salem": ("Salem", 11.6643, 78.1460),
    "tirunelveli": ("Tirunelveli", 8.7139, 77.7567),
    "vellore": ("Vellore", 12.9165, 79.1325),
    "erode": ("Erode", 11.3410, 77.7172),
    "thanjavur": ("Thanjavur", 10.7870, 79.1378),
    "kanchipuram": ("Kanchipuram", 12.8342, 79.7036),
    "kumbakonam": ("Kumbakonam", 10.9602, 79.3845),
    "rameswaram": ("Rameswaram", 9.2876, 79.3129),
    # Telangana / Andhra Pradesh
    "hyderabad": ("Hyderabad", 17.3850, 78.4867),
    "warangal": ("Warangal", 17.9689, 79.5941),
    "visakhapatnam": ("Visakhapatnam", 17.6868, 83.2185),
    "vijayawada": ("Vijayawada", 16.5062, 80.6480),
    "guntur": ("Guntur", 16.3067, 80.4365),
    "tirupati": ("Tirupati", 13.6288, 79.4192),
    "nellore": ("Nellore", 14.4426, 79.9865),
    "rajahmundry": ("Rajahmundry", 17.0005, 81.8040),
    # Karnataka
    "bengaluru": ("Bengaluru", 12.9716, 77.5946),
    "mysuru": ("Mysuru", 12.2958, 76.6394),
    "mangaluru": ("Mangaluru", 12.9141, 74.8560),
    "hubballi": ("Hubballi", 15.3647, 75.1240),
    "belagavi": ("Belagavi", 15.8497, 74.4977),
    "udupi": ("Udupi", 13.3409, 74.7421),
    # Kerala
    "thiruvananthapuram": ("Thiruvananthapuram", 8.5241, 76.9366),
    "kochi": ("Kochi", 9.9312, 76.2673),
    "kozhikode": ("Kozhikode", 11.2588, 75.7804),
    "thrissur": ("Thrissur", 10.5276, 76.2144),
    "kollam": ("Kollam", 8.8932, 76.6141),
    "guruvayur": ("Guruvayur", 10.5949, 76.0400),
    "palakkad": ("Palakkad", 10.7867, 76.6548),
    # Maharashtra
    "mumbai": ("Mumbai", 19.0760, 72.8777),
    "pune": ("Pune", 18.5204, 73.8567),
    "nagpur": ("Nagpur", 21.1458, 79.0882),
    "nashik": ("Nashik", 19.9975, 73.7898),
    "aurangabad": ("Aurangabad", 19.8762, 75.3433),
    "shirdi": ("Shirdi", 19.7645, 74.4763),
    "kolhapur": ("Kolhapur", 16.7050, 74.2433),
    # North India
    "delhi": ("Delhi", 28.7041, 77.1025),
    "jaipur": ("Jaipur", 26.9124, 75.7873),
    "lucknow": ("Lucknow", 26.8467, 80.9462),
    "kanpur": ("Kanpur", 26.4499, 80.3319),
    "varanasi": ("Varanasi", 25.3176, 82.9739),
    "prayagraj": ("Prayagraj", 25.4358, 81.8463),
    "haridwar": ("Haridwar", 29.9457, 78.1642),
    "rishikesh": ("Rishikesh", 30.0869, 78.2676),
    "mathura": ("Mathura", 27.4924, 77.6737),
    "ayodhya": ("Ayodhya", 26.7922, 82.1998),
    "amritsar": ("Amritsar", 31.6340, 74.8723),
    "chandigarh": ("Chandigarh", 30.7333, 76.7794),
    "dehradun": ("Dehradun", 30.3165, 78.0322),
    "agra": ("Agra", 27.1767, 78.0081),
    "patna": ("Patna", 25.5941, 85.1376),
    "gaya": ("Gaya", 24.7955, 85.0002),
    "ujjain": ("Ujjain", 23.1793, 75.7849),
    "indore": ("Indore", 22.7196, 75.8577),
    "bhopal": ("Bhopal", 23.2599, 77.4126),
    "gwalior": ("Gwalior", 26.2183, 78.1828),
    # West / East
    "ahmedabad": ("Ahmedabad", 23.0225, 72.5714),
    "surat": ("Surat", 21.1702, 72.8311),
    "vadodara": ("Vadodara", 22.3072, 73.1812),
    "rajkot": ("Rajkot", 22.3039, 70.8022),
    "dwarka": ("Dwarka", 22.2442, 68.9685),
    "kolkata": ("Kolkata", 22.5726, 88.3639),
    "bhubaneswar": ("Bhubaneswar", 20.2961, 85.8245),
    "puri": ("Puri", 19.8135, 85.8312),
    "guwahati": ("Guwahati", 26.1445, 91.7362),
    "ranchi": ("Ranchi", 23.3441, 85.3096),
    "raipur": ("Raipur", 21.2514, 81.6296),
    # Diaspora (timezone estimated from longitude; DST-unaware)
    "colombo": ("Colombo", 6.9271, 79.8612),
    "kathmandu": ("Kathmandu", 27.7172, 85.3240),
    "singapore": ("Singapore", 1.3521, 103.8198),
    "kuala-lumpur": ("Kuala Lumpur", 3.1390, 101.6869),
    "dubai": ("Dubai", 25.2048, 55.2708),
    "london": ("London", 51.5074, -0.1278),
    "new-york": ("New York", 40.7128, -74.0060),
    "toronto": ("Toronto", 43.6532, -79.3832),
    "san-francisco": ("San Francisco", 37.7749, -122.4194),
    "sydney": ("Sydney", -33.8688, 151.2093),
}
