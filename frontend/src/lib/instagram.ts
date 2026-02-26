/**
 * Instagram Image Scraper Utilities
 *
 * Fetches fresh image URLs from Instagram post pages
 * to avoid expired signature issues.
 */

/**
 * Extract image URL from Instagram post page HTML
 * Instagram serves images with time-based signatures that expire,
 * so we need to scrape the fresh URL from the page itself.
 */
export async function getInstagramImageUrl(postUrl: string): Promise<string | null> {
  try {
    // Use a CORS proxy or backend endpoint to fetch Instagram page
    // For now, we'll try direct fetch first
    const response = await fetch(postUrl)

    if (!response.ok) {
      console.error('[Instagram] Failed to fetch page:', response.status)
      return null
    }

    const html = await response.text()

    // Instagram embeds the image URL in several places:
    // 1. OpenGraph meta tag: <meta property="og:image" content="...">
    // 2. Twitter card: <meta name="twitter:image" content="...">
    // 3. Direct img tag with class containing "x5yr21d" or similar

    // Try OpenGraph first
    const ogImageMatch = html.match(/<meta[^>]+property=["']og:image["'][^>]+content=["']([^"']+)["']/)
    if (ogImageMatch && ogImageMatch[1]) {
      // Instagram uses HTML entities in meta tags, decode them
      const imageUrl = ogImageMatch[1].replace(/&amp;/g, '&')
      console.log('[Instagram] Found image via og:image:', imageUrl.substring(0, 100))
      return imageUrl
    }

    // Try Twitter card
    const twitterImageMatch = html.match(/<meta[^>]+name=["']twitter:image["'][^>]+content=["']([^"']+)["']/)
    if (twitterImageMatch && twitterImageMatch[1]) {
      const imageUrl = twitterImageMatch[1].replace(/&amp;/g, '&')
      console.log('[Instagram] Found image via twitter:image:', imageUrl.substring(0, 100))
      return imageUrl
    }

    // Try img tag pattern (backup)
    const imgMatch = html.match(/<img[^>]+class=["'][^"']*x5yr21d[^"']*["'][^>]+src=["']([^"']+)["']/)
    if (imgMatch && imgMatch[1]) {
      const imageUrl = imgMatch[1].replace(/&amp;/g, '&')
      console.log('[Instagram] Found image via img tag:', imageUrl.substring(0, 100))
      return imageUrl
    }

    console.error('[Instagram] Could not find image URL in page')
    return null
  } catch (error) {
    console.error('[Instagram] Error fetching image URL:', error)
    return null
  }
}

/**
 * Check if an image URL is from Instagram
 */
export function isInstagramImageUrl(url: string): boolean {
  return url.includes('cdninstagram.com') ||
         url.includes('fbcdn.net') ||
         url.includes('instagram.com')
}

/**
 * Get a fresh Instagram image URL via backend proxy
 * This avoids CORS issues and gets the latest valid signature
 */
export async function getFreshInstagramImageUrl(postUrl: string): Promise<string | null> {
  try {
    // Call backend endpoint to scrape fresh image URL
    const response = await fetch(`/api/v1/instagram-image?post_url=${encodeURIComponent(postUrl)}`)

    if (!response.ok) {
      console.error('[Instagram] Backend proxy failed:', response.status, await response.text())
      return null
    }

    const data = await response.json()
    return data.image_url || null
  } catch (error) {
    console.error('[Instagram] Error calling backend proxy:', error)
    return null
  }
}
