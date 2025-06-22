// In your main cyberpulse folder, in blog.js

document.addEventListener('DOMContentLoaded', () => {
    const postContainer = document.getElementById('post-list-container');

    fetch('blog-index.json')
        .then(response => response.json())
        .then(posts => {
            if (!posts || posts.length === 0) {
                postContainer.innerHTML = '<p style="text-align: center;">No posts yet. The automation will add one soon!</p>';
                return;
            }
            
            let allPostsHTML = '';
            posts.forEach(post => {
                let categoryTag = '';
                // **NEW**: If a category exists, make it a clickable link
                if (post.category) {
                    const categorySlug = post.category.toLowerCase().replace(' ', '-');
                    const categoryUrl = `category-${categorySlug}.html`;
                    categoryTag = `<a href="${categoryUrl}" class="category-tag">${post.category}</a>`;
                }

                allPostsHTML += `
                    <a href="${post.url}" class="post-link">
                        ${categoryTag}
                        <h2>${post.title}</h2>
                        <p>${post.summary}</p>
                    </a>
                `;
            });
            postContainer.innerHTML = allPostsHTML;
        })
        .catch(error => {
            console.error('Error fetching blog index:', error);
            postContainer.innerHTML = '<p>Error loading posts.</p>';
        });
});