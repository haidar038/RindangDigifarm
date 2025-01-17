const API_URL = 'https://data.bmkg.go.id/DataMKG/MEWS/DigitalForecast/DigitalForecast-MalukuUtara.xml';
const AREA_ID = '501394';
const DAYS_OF_WEEK = ['Minggu', 'Senin', 'Selasa', 'Rabu', 'Kamis', "Jum'at", 'Sabtu'];
const WEATHER_DESCRIPTIONS = {
    0: ['Cerah', 'sunny'],
    1: ['Cerah Berawan', 'sunny'],
    2: ['Cerah Berawan', 'sunny'],
    3: ['Berawan', 'cloudy'],
    4: ['Berawan Tebal', 'cloudy'],
    5: ['Udara Kabur', 'cloudy'],
    10: ['Asap', 'cloudy'],
    45: ['Kabut', 'cloudy'],
    60: ['Hujan Ringan', 'rainy'],
    61: ['Hujan Sedang', 'rainy'],
    63: ['Hujan Lebat', 'rainy'],
    80: ['Hujan Lokal', 'rainy'],
    95: ['Hujan Petir', 'thunderstorm'],
    97: ['Hujan Petir', 'thunderstorm'],
};

async function fetchWeatherData() {
    try {
        const response = await fetch(API_URL);
        const xmlString = await response.text();
        const parser = new DOMParser();
        const xmlDoc = parser.parseFromString(xmlString, 'text/xml');
        return processWeatherData(xmlDoc);
    } catch (error) {
        console.error('Error fetching or parsing XML data:', error);
        return null;
    }
}

function processWeatherData(xmlDoc) {
    const area = xmlDoc.querySelector(`area[id="${AREA_ID}"]`);
    if (!area) {
        console.log(`Area dengan ID ${AREA_ID} tidak ditemukan.`);
        return null;
    }

    const extractData = (paramId, unit) => {
        return Array.from(area.querySelector(`parameter[id="${paramId}"]`).querySelectorAll('timerange')).map((timerange) => timerange.querySelector(`value[unit="${unit}"]`).textContent);
    };

    return {
        humidity: extractData('hu', '%'),
        temperature: extractData('t', 'C'),
        weather: extractData('weather', 'icon'),
        windDirection: extractData('wd', 'deg'),
        windSpeed: extractData('ws', 'Kt'),
    };
}
