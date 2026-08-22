/**
 * FRONTEND PERFORMANCE OPTIMIZER
 * Code splitting, lazy loading, and ultra-fast rendering
 * Target: SSS+++++ Grade Performance
 */

const PerformanceOptimizer = {
    /**
     * Lazy load images when they enter viewport
     */
    lazyLoadImages() {
        const images = document.querySelectorAll('img[loading="lazy"]');

        if ('IntersectionObserver' in window) {
            const imageObserver = new IntersectionObserver((entries, observer) => {
                entries.forEach(entry => {
                    if (entry.isIntersecting) {
                        const img = entry.target;
                        if (img.dataset.src) {
                            img.src = img.dataset.src;
                            img.removeAttribute('data-src');
                        }
                        observer.unobserve(img);
                    }
                });
            });

            images.forEach(img => imageObserver.observe(img));
        }
    },

    /**
     * Debounce function for performance
     */
    debounce(func, wait = 300) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    },

    /**
     * Throttle function for performance
     */
    throttle(func, limit = 100) {
        let inThrottle;
        return function (...args) {
            if (!inThrottle) {
                func.apply(this, args);
                inThrottle = true;
                setTimeout(() => inThrottle = false, limit);
            }
        };
    },

    /**
     * Preload critical resources
     */
    preloadCriticalResources() {
        const preloads = [
            { href: '/static/css/admin.css', as: 'style' }
        ];

        preloads.forEach(resource => {
            const alreadyLoaded = document.querySelector(
                `link[href="${resource.href}"], script[src="${resource.href}"]`
            );
            const alreadyPreloaded = document.querySelector(
                `link[rel="preload"][href="${resource.href}"]`
            );
            if (alreadyLoaded || alreadyPreloaded) return;

            const link = document.createElement('link');
            link.rel = 'preload';
            link.href = resource.href;
            link.as = resource.as;
            document.head.appendChild(link);
        });
    },

    /**
     * Virtual scrolling for large lists
     */
    createVirtualScroller(container, items, renderItem, itemHeight = 50) {
        const viewportHeight = container.clientHeight;
        const visibleCount = Math.ceil(viewportHeight / itemHeight) + 2;
        let scrollTop = 0;

        const render = () => {
            const startIndex = Math.floor(scrollTop / itemHeight);
            const endIndex = Math.min(startIndex + visibleCount, items.length);

            container.innerHTML = '';
            const fragment = document.createDocumentFragment();

            for (let i = startIndex; i < endIndex; i++) {
                const element = renderItem(items[i], i);
                element.style.position = 'absolute';
                element.style.top = `${i * itemHeight}px`;
                fragment.appendChild(element);
            }

            container.appendChild(fragment);
            container.style.height = `${items.length * itemHeight}px`;
        };

        const handleScroll = this.throttle(() => {
            scrollTop = container.scrollTop;
            render();
        }, 16); // 60 FPS

        container.addEventListener('scroll', handleScroll);
        render();

        return { render, destroy: () => container.removeEventListener('scroll', handleScroll) };
    },

    /**
     * Optimize API calls with request caching
     */
    cachedFetch: (() => {
        const cache = new Map();
        const cacheTTL = 5 * 60 * 1000; // 5 minutes

        return async (url, options = {}) => {
            const cacheKey = JSON.stringify({ url, ...options });
            const now = Date.now();

            // Check cache
            if (cache.has(cacheKey)) {
                const { data, timestamp } = cache.get(cacheKey);
                if (now - timestamp < cacheTTL) {
                    console.log('📦 Cache HIT:', url);
                    return Promise.resolve(data);
                }
            }

            // Fetch and cache
            try {
                const response = await fetch(url, options);
                const data = await response.json();
                cache.set(cacheKey, { data, timestamp: now });

                // Clean old cache entries
                if (cache.size > 100) {
                    const oldestKey = cache.keys().next().value;
                    cache.delete(oldestKey);
                }

                return data;
            } catch (error) {
                throw error;
            }
        };
    })(),

    /**
     * Resource hints for better performance
     */
    addResourceHints() {
        // DNS prefetch for external resources
        const dnsPrefetch = [
            'https://fonts.googleapis.com',
            'https://cdnjs.cloudflare.com'
        ];

        dnsPrefetch.forEach(domain => {
            const link = document.createElement('link');
            link.rel = 'dns-prefetch';
            link.href = domain;
            document.head.appendChild(link);
        });

        // Preconnect to API
        const preconnect = document.createElement('link');
        preconnect.rel = 'preconnect';
        preconnect.href = window.location.origin;
        document.head.appendChild(preconnect);
    },

    /**
     * Monitor and log performance metrics
     */
    monitorPerformance() {
        if ('PerformanceObserver' in window) {
            // Monitor long tasks
            const observer = new PerformanceObserver((list) => {
                for (const entry of list.getEntries()) {
                    if (entry.duration > 50) {
                        console.warn('⚠️ Long task detected:', entry.duration.toFixed(2), 'ms');
                    }
                }
            });

            try {
                observer.observe({ entryTypes: ['longtask'] });
            } catch (e) {
                // longtask not supported
            }
        }

        // Log Core Web Vitals
        if ('web-vital' in window) {
            // Would use web-vitals library here
        }
    },

    /**
     * Initialize all optimizations
     */
    init() {
        console.log('🚀 Performance Optimizer initializing...');

        this.preloadCriticalResources();
        this.addResourceHints();
        this.lazyLoadImages();
        this.monitorPerformance();

        // Make debounce and throttle globally available
        window.debounce = this.debounce.bind(this);
        window.throttle = this.throttle.bind(this);

        console.log('✅ Performance Optimizer ready!');
        console.log('   - Lazy image loading');
        console.log('   - API request caching');
        console.log('   - Resource hints');
        console.log('   - Performance monitoring');
    }
};
