echo "# auto-upload-bantin" >> README.md
git init
git add upbantin.md
git commit -m "first commit"
git branch -M main
git remote add origin https://github.com/thoitietqtri/auto-upload-bantin.git
git push -u origin main