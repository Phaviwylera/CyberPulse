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
                const categoryTag = post.category ? `<span class="category-tag">${post.category}</span>` : '';

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